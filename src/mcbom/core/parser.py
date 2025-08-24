import os
import json
from pathlib import Path
import zipfile
import re

# TODO(roadmap-parser):
# - Support more recipe types beyond crafting_shaped/shapeless (smelting/blasting/stonecutting/etc.).
# - Normalize outputs (counts) consistently across different schemas (e.g., result/output forms).
# - Resolve tags with configurable preference strategy (namespace priority, allowlist/denylist).
# - Optional importer: merge JEI/RecipeManager dumps into the in-memory registry.
# - Improve logging (structured) and error handling for malformed JSON entries.

def load_recipes(base_path: str):
    """Load recipe JSONs and select the best recipe per output item.

    Preference order when multiple recipes produce the same item:
    1) Parseable by our engine (minecraft:crafting_shaped/shapeless)
    2) Other minecraft:* types
    3) Other mod types
    On ties, prefer on-disk datapacks over JAR-embedded recipes.

    Supported layouts under base_path:
      - data/*/recipes/**/*.json                      (datapack standard)
      - */recipes/**/*.json                           (legacy fallback)
      - kubejs/data/*/recipes/**/*.json               (KubeJS)
      - config/openloader/data/**/data/*/recipes/**/*.json (OpenLoader)
      - global_packs/**/data/*/recipes/**/*.json      (FTB/Global packs)
      - datapacks/**/data/*/recipes/**/*.json         (Global datapacks)
    Additionally, if `<base_path>/mods/*.jar` exists, scans JAR entries at
    `data/*/recipes/**/*.json` and `data/*/recipe/**/*.json`.
    """
    # Keep best candidate per output item: (score_tuple, recipe_dict)
    # score_tuple = (is_parseable, type_priority, source_rank)
    #   is_parseable: 1 if minecraft:crafting_shaped/shapeless else 0
    #   type_priority: 2 for supported crafting, 1 for other minecraft:*, 0 otherwise
    #   source_rank: 1 for on-disk, 0 for jar (prefer on-disk on ties)
    best = {}
    root_path = Path(base_path)

    # Gather candidate recipe files from multiple common locations
    recipe_paths = set()
    scan_roots = [
        root_path,
        root_path / 'kubejs',
        root_path / 'config' / 'openloader' / 'data',
        root_path / 'global_packs',
        root_path / 'datapacks',
        root_path / 'reports',               # vanilla /debug report (sometimes unzipped)
        root_path / 'debug' / 'reports',     # vanilla /debug report common path
    ]
    for rp in scan_roots:
        if not rp.exists():
            continue
        # Standard datapack layout anywhere under this root
        for p in rp.rglob('**/data/*/recipes/**/*.json'):
            sp = str(p).replace('\\', '/').lower()
            if '/advancement/' in sp or '/advancements/' in sp:
                continue
            recipe_paths.add(p)
        # Also support singular 'recipe' (seen in some KubeJS packs)
        for p in rp.rglob('**/data/*/recipe/**/*.json'):
            sp = str(p).replace('\\', '/').lower()
            if '/advancement/' in sp or '/advancements/' in sp:
                continue
            recipe_paths.add(p)
        # Legacy layout (some tools write <root>/<ns>/recipes/...)
        for p in rp.rglob('**/*/recipes/**/*.json'):
            sp = str(p).replace('\\', '/').lower()
            if '/advancement/' in sp or '/advancements/' in sp:
                continue
            recipe_paths.add(p)
        # Legacy singular 'recipe'
        for p in rp.rglob('**/*/recipe/**/*.json'):
            sp = str(p).replace('\\', '/').lower()
            if '/advancement/' in sp or '/advancements/' in sp:
                continue
            recipe_paths.add(p)

    recipe_files = sorted(recipe_paths, key=lambda p: str(p))
    print(f"Parser: Found {len(recipe_files)} recipe files under '{base_path}'.")

    def _extract_result_item(data: dict):
        # Common cases: 'result' can be a string or an object with 'item' or 'id'
        if 'result' in data:
            res = data['result']
            if isinstance(res, str):
                return res
            if isinstance(res, dict):
                return res.get('item') or res.get('id')
        # Some mods use 'output'
        if 'output' in data:
            out = data['output']
            if isinstance(out, str):
                return out
            if isinstance(out, dict):
                return out.get('item') or out.get('id')
        # Some mods (e.g., Create) use 'results': [ ... ]
        if 'results' in data and isinstance(data['results'], list) and data['results']:
            first = data['results'][0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get('item') or first.get('id')
        return None

    def _score_tuple(data: dict, source_rank: int):
        rtype = data.get('type', '') or ''
        # Structural parseability: shaped if has pattern+key; shapeless if has ingredients list
        has_shaped = isinstance(data.get('pattern'), list) and isinstance(data.get('key'), dict)
        has_shapeless = isinstance(data.get('ingredients'), list)
        # AE2 inscriber: ingredients is an object with top/middle/bottom
        has_inscriber = (isinstance(rtype, str) and rtype.endswith(':inscriber') and isinstance(data.get('ingredients'), dict) and data['ingredients'].get('middle') is not None)
        parseable = 1 if (has_shaped or has_shapeless or has_inscriber) else 0
        if parseable and rtype in {"minecraft:crafting_shaped", "minecraft:crafting_shapeless"}:
            tprio = 2
        elif isinstance(rtype, str) and rtype.startswith("minecraft:"):
            tprio = 1
        else:
            tprio = 0
        return (parseable, tprio, source_rank)

    def _consider(out_item: str, data: dict, source_rank: int):
        score = _score_tuple(data, source_rank)
        prev = best.get(out_item)
        if prev is None or score > prev[0]:
            best[out_item] = (score, data)

    for file_path in recipe_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            out_item = _extract_result_item(data)
            if out_item:
                _consider(out_item, data, source_rank=1)  # on-disk datapack

    # Also scan mod jars if present
    mods_dir = root_path / 'mods'
    if mods_dir.exists() and mods_dir.is_dir():
        jar_files = list(mods_dir.glob('*.jar'))
        print(f"Parser: Scanning {len(jar_files)} mod JAR(s) for recipes...")
        for jar_path in jar_files:
            try:
                with zipfile.ZipFile(jar_path, 'r') as zf:
                    for name in zf.namelist():
                        # Match datapack-like recipe paths inside JAR
                        if not name.endswith('.json'):
                            continue
                        if not name.startswith('data/'):
                            continue
                        # Accept both 'recipes' and singular 'recipe', exclude advancements
                        if ('/recipes/' not in name and '/recipe/' not in name) or ('/advancement/' in name or '/advancements/' in name):
                            continue
                        try:
                            with zf.open(name) as fp:
                                # Ensure text decode for robustness
                                raw = fp.read()
                                data = json.loads(raw.decode('utf-8', errors='ignore'))
                                key = _extract_result_item(data)
                                if key:
                                    # Consider JAR candidate; will only win if it scores better
                                    _consider(key, data, source_rank=0)
                        except Exception:
                            # Skip invalid/unsupported JSON entries gracefully
                            continue
            except zipfile.BadZipFile:
                continue

    # Ingest KubeJS server script custom recipes (self-sufficient, no extra mods)
    # We target blocks like: event.custom({ type: 'ae2:inscriber', ingredients: { ... }, result: {...} })
    def _extract_custom_blocks(text: str):
        blocks = []
        anchor = 'event.custom'
        i = 0
        L = len(text)
        while True:
            j = text.find(anchor, i)
            if j == -1:
                break
            # find first '{' after 'event.custom('
            k = text.find('(', j)
            if k == -1:
                i = j + len(anchor)
                continue
            # Skip whitespace to '{'
            m = text.find('{', k)
            if m == -1:
                i = k + 1
                continue
            # Brace matching
            depth = 0
            end = m
            while end < L:
                ch = text[end]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        # include '}'
                        end += 1
                        break
                end += 1
            if depth == 0 and end <= L:
                blocks.append(text[m:end])
                i = end
            else:
                # Unbalanced; move forward to avoid infinite loop
                i = j + len(anchor)
        return blocks

    def _jsonish_to_dict(s: str):
        # Convert single quotes to double quotes
        s2 = s.replace("\r", "").replace("\n", "\n")
        s2 = re.sub(r"'", '"', s2)
        # Quote unquoted object keys: { key: ... } -> { "key": ... }
        s2 = re.sub(r'([,{]\s*)([A-Za-z_][A-Za-z0-9_\-]*)\s*:', r'\1"\2":', s2)
        # Remove trailing commas before } or ]
        s2 = re.sub(r',\s*([}\]])', r'\1', s2)
        try:
            return json.loads(s2)
        except Exception:
            return None

    # Scan KubeJS server scripts for event.custom blocks
    kubejs_script_roots = [root_path / 'kubejs']
    for skr in kubejs_script_roots:
        if not skr.exists():
            continue
        js_files = set()
        for p in skr.rglob('server_scripts/**/*.js'):
            js_files.add(p)
        for p in skr.rglob('server_scripts/*.js'):
            js_files.add(p)
        for js_path in sorted(js_files, key=lambda q: str(q)):
            try:
                txt = js_path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            for blk in _extract_custom_blocks(txt):
                data = _jsonish_to_dict(blk)
                if not isinstance(data, dict):
                    continue
                rtype = str(data.get('type') or '')
                if rtype.endswith(':inscriber'):
                    out_item = _extract_result_item(data)
                    if out_item:
                        _consider(out_item, data, source_rank=1)
    # Materialize best candidates into return map
    recipes = {item: rec for item, (score, rec) in best.items()}

    # Inject minimal vanilla fallbacks for core items if no parseable recipe is present.
    def _has_parseable(item_id: str) -> bool:
        rec = recipes.get(item_id)
        return bool(rec and rec.get('type') in {"minecraft:crafting_shaped", "minecraft:crafting_shapeless"})

    # minecraft:stick (4) from planks -> use oak_planks to avoid tag dependency if tags missing
    if not _has_parseable("minecraft:stick"):
        recipes["minecraft:stick"] = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["X", "X"],
            "key": {"X": {"item": "minecraft:oak_planks"}},
            "result": {"item": "minecraft:stick", "count": 4},
        }

    # minecraft:oak_planks (4) from oak_log
    if not _has_parseable("minecraft:oak_planks"):
        recipes["minecraft:oak_planks"] = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:oak_log"}],
            "result": {"item": "minecraft:oak_planks", "count": 4},
        }

    # minecraft:diamond_pickaxe (1) from 3x diamond + 2x stick
    if not _has_parseable("minecraft:diamond_pickaxe"):
        recipes["minecraft:diamond_pickaxe"] = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["XXX", " Y ", " Y "],
            "key": {
                "X": {"item": "minecraft:diamond"},
                "Y": {"item": "minecraft:stick"}
            },
            "result": {"item": "minecraft:diamond_pickaxe", "count": 1},
        }

    # Placeholder fallback for AE2 Controller if not found in datapacks/JARs.
    # NOTE: This is a placeholder (approximate) recipe to keep BOM functional for modpack analysis.
    # It will be clearly marked and should be replaced by real recipes when available.
    if not recipes.get("ae2:controller") and not recipes.get("appliedenergistics2:controller"):
        recipes["ae2:controller"] = {
            "type": "minecraft:crafting_shaped",
            "pattern": [
                "XAX",
                "ASA",
                "XAX"
            ],
            "key": {
                "X": {"item": "ae2:fluix_block"},
                "A": {"item": "ae2:engineering_processor"},
                "S": {"item": "ae2:sky_stone_block"}
            },
            "result": {"item": "ae2:controller", "count": 1},
            "x_mcbom_placeholder": True
        }

    return recipes

def load_tags(base_path: str):
    """
    Loads all item tag .json files from datapack directories.

    Supported layouts under base_path:
      - data/*/tags/items/**/*.json  (NeoForge/Forge datapack standard)
      - */tags/items/**/*.json       (legacy fallback)
    Additionally, scans `<base_path>/mods/*.jar` for `data/*/tags/items/**/*.json`
    and merges them (without overriding on-disk datapacks).
    """
    tags = {}
    root_path = Path(base_path)
    # Gather candidate tag files from multiple locations
    tag_paths = set()
    tag_scan_roots = [
        root_path,
        root_path / 'kubejs',
        root_path / 'config' / 'openloader' / 'data',
        root_path / 'global_packs',
        root_path / 'datapacks',
        root_path / 'reports',
        root_path / 'debug' / 'reports',
    ]
    for rp in tag_scan_roots:
        if not rp.exists():
            continue
        for p in rp.rglob('**/data/*/tags/items/**/*.json'):
            tag_paths.add(p)
        for p in rp.rglob('**/*/tags/items/**/*.json'):
            tag_paths.add(p)

    tag_files = sorted(tag_paths, key=lambda p: str(p))

    print(f"Parser: Found {len(tag_files)} tag files under '{base_path}'.")

    for file_path in tag_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # The key is constructed from the namespace (parent dir) and filename.
            # e.g., <base>/data/minecraft/tags/items/planks.json -> minecraft:planks
            # or legacy: <base>/minecraft/tags/items/planks.json -> minecraft:planks
            namespace = file_path.parent.parent.parent.name
            tag_name = file_path.stem
            full_tag_name = f"{namespace}:{tag_name}"
            tags[full_tag_name] = data.get('values', [])

    # Scan mod jars for tags
    mods_dir = root_path / 'mods'
    if mods_dir.exists() and mods_dir.is_dir():
        jar_files = list(mods_dir.glob('*.jar'))
        print(f"Parser: Scanning {len(jar_files)} mod JAR(s) for tags...")
        for jar_path in jar_files:
            try:
                with zipfile.ZipFile(jar_path, 'r') as zf:
                    for name in zf.namelist():
                        if not name.endswith('.json'):
                            continue
                        if '/tags/items/' not in name or not name.startswith('data/'):
                            continue
                        try:
                            with zf.open(name) as fp:
                                raw = fp.read()
                                data = json.loads(raw.decode('utf-8', errors='ignore'))
                                # Build tag key from path: data/<ns>/tags/items/<tag>.json
                                parts = name.split('/')
                                # parts: ['data', '<ns>', 'tags', 'items', '<tag>.json', ...]
                                if len(parts) >= 5:
                                    ns = parts[1]
                                    tag_file = parts[4]
                                    tag_name = Path(tag_file).stem
                                    full_tag = f"{ns}:{tag_name}"
                                    if full_tag not in tags:
                                        tags[full_tag] = data.get('values', [])
                        except Exception:
                            continue
            except zipfile.BadZipFile:
                continue

    return tags


if __name__ == '__main__':
    # Test the parser with our instance directory
    instance_path = 'instance'
    print(f"--- Loading data from: {instance_path} ---")

    loaded_recipes = load_recipes(instance_path)
    print(f"\n--- Loaded Recipes ({len(loaded_recipes)}) ---")
    print(json.dumps(loaded_recipes, indent=2))

    loaded_tags = load_tags(instance_path)
    print(f"\n--- Loaded Tags ({len(loaded_tags)}) ---")
    print(json.dumps(loaded_tags, indent=2))
