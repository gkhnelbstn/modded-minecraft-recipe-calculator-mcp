import os
import json
from pathlib import Path
import zipfile

# TODO(roadmap-parser):
# - Support more recipe types beyond crafting_shaped/shapeless (smelting/blasting/stonecutting/etc.).
# - Normalize outputs (counts) consistently across different schemas (e.g., result/output forms).
# - Resolve tags with configurable preference strategy (namespace priority, allowlist/denylist).
# - Optional importer: merge JEI/RecipeManager dumps into the in-memory registry.
# - Improve logging (structured) and error handling for malformed JSON entries.

def load_recipes(base_path: str):
    """
    Loads all recipe .json files from datapack directories.

    Supported layouts under base_path:
      - data/*/recipes/**/*.json   (NeoForge/Forge datapack standard)
      - */recipes/**/*.json        (legacy fallback)
    Additionally, if `<base_path>/mods/*.jar` exists, scans JAR entries at
    `data/*/recipes/**/*.json` and merges them (without overriding on-disk datapacks).
    """
    recipes = {}
    root_path = Path(base_path)
    # Prefer standard datapack location
    recipe_files = list(root_path.glob('data/*/recipes/**/*.json'))
    # Fallback to legacy layout if nothing found
    if not recipe_files:
        recipe_files = list(root_path.glob('*/recipes/**/*.json'))

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
        return None

    for file_path in recipe_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            out_item = _extract_result_item(data)
            if out_item:
                recipes[out_item] = data

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
                        if '/recipes/' not in name or not name.startswith('data/'):
                            continue
                        try:
                            with zf.open(name) as fp:
                                # Ensure text decode for robustness
                                raw = fp.read()
                                data = json.loads(raw.decode('utf-8', errors='ignore'))
                                key = _extract_result_item(data)
                                if key and key not in recipes:  # don't override on-disk
                                    recipes[key] = data
                        except Exception:
                            # Skip invalid/unsupported JSON entries gracefully
                            continue
            except zipfile.BadZipFile:
                continue
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
    tag_files = list(root_path.glob('data/*/tags/items/**/*.json'))
    if not tag_files:
        tag_files = list(root_path.glob('*/tags/items/**/*.json'))

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
                                data = json.load(fp)
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
