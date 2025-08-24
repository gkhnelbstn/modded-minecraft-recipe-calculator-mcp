import json
from collections import Counter
from mcbom.core.parser import load_recipes, load_tags
from typing import List, Dict, Tuple

# Namespace alias map (canonicalize to short forms)
NS_ALIASES = {
    "appliedenergistics2": "ae2",
    "ae2": "ae2",
}

# TODO(roadmap-engine):
# - Multiple recipe options per item with deterministic preference order (configurable).
# - Improve cycle detection diagnostics; expose cycle path in analysis.
# - Memoization granularity and cache invalidation when preferences change.
# - Performance profiling for deep graphs; consider iterative DFS to reduce recursion depth.
# - Extend support for non-crafting recipe types (aligned with parser roadmap).
class BomEngine:
    def __init__(self, recipes_data, tags_data):
        self.recipes = recipes_data
        self.tags = tags_data
        self.memo = {}  # Memoization cache

        # Ensure recipe keys are accessible via canonical namespaces
        self._apply_namespace_aliases()

    def _canon(self, item_id: str) -> str:
        """Return canonical item id by normalizing known namespace aliases.

        Args:
            item_id: e.g., 'appliedenergistics2:controller'
        Returns:
            Canonical id, e.g., 'ae2:controller'
        """
        if not isinstance(item_id, str) or ":" not in item_id:
            return item_id
        ns, name = item_id.split(":", 1)
        ns2 = NS_ALIASES.get(ns, ns)
        return f"{ns2}:{name}"

    def _apply_namespace_aliases(self) -> None:
        """Add canonical-key entries for any recipe keyed by an alias namespace."""
        new_map = dict(self.recipes)
        for key, val in list(self.recipes.items()):
            canon = self._canon(key)
            if canon not in new_map:
                new_map[canon] = val
        self.recipes = new_map

    def _output_count(self, recipe: dict) -> int:
        """Return the produced item count for a recipe.

        Supports schemas where 'result' or 'output' can be a dict or a string.
        Defaults to 1 when not specified.
        """
        res = recipe.get('result')
        if isinstance(res, dict):
            c = res.get('count')
            if isinstance(c, (int, float)):
                return int(c)
        elif isinstance(res, str):
            return 1
        out = recipe.get('output')
        if isinstance(out, dict):
            c = out.get('count')
            if isinstance(c, (int, float)):
                return int(c)
        return 1

    def analyze(self, item_id: str, quantity: int = 1) -> Dict:
        """
        Analyzes the target item and returns a structured result with:
        - target, quantity
        - total_raw_materials: list[{item, count}]
        - steps: list of production steps with recipe_type and ingredients

        Args:
            item_id: fully-qualified item id (e.g., 'minecraft:stick')
            quantity: target quantity

        Returns:
            A dictionary ready for JSON serialization and diagram generation.
        """
        raw_counter, steps = self.calculate_with_steps(item_id, quantity)
        # Convert Counter to sorted list of dicts for stable output
        total_raw_materials = [
            {"item": k, "count": v} for k, v in sorted(raw_counter.items(), key=lambda x: x[0])
        ]
        return {
            "target": item_id,
            "quantity": quantity,
            "total_raw_materials": total_raw_materials,
            "steps": steps,
        }

    def calculate_raw_materials(self, item_id, quantity=1, visited=None):
        """
        Recursively calculates the raw materials for a given item.
        """
        # Canonicalize for stable lookups and memoization
        item_id = self._canon(item_id)
        if item_id in self.memo:
            # If result is cached, scale it and return
            return self._scale_counter(self.memo[item_id], quantity)

        if visited is None:
            visited = set()

        # Cycle detection
        if item_id in visited:
            print(f"Warning: Cycle detected at {item_id}. Treating as raw material.")
            return Counter({item_id: quantity})

        visited.add(item_id)

        # Base case: If the item has no recipe, it's a raw material.
        if item_id not in self.recipes:
            visited.remove(item_id)
            return Counter({item_id: quantity})

        # Recursive step
        raw_materials = Counter()
        recipe = self.recipes[item_id]
        recipe_output_count = self._output_count(recipe)
        crafting_multiplier = quantity / recipe_output_count

        ingredients = self._get_ingredients_from_recipe(recipe)
        # If unsupported type (no parseable ingredients) treat as raw material
        rtype = recipe.get('type', '') or ''
        if not ingredients and rtype not in {"minecraft:crafting_shaped", "minecraft:crafting_shapeless"}:
            visited.remove(item_id)
            return Counter({item_id: quantity})

        for ingredient in ingredients:
            ingredient_id = self._canon(ingredient['item'])
            ingredient_qty = ingredient['quantity'] * crafting_multiplier

            sub_materials = self.calculate_raw_materials(ingredient_id, ingredient_qty, visited.copy())
            raw_materials.update(sub_materials)

        # Memoize the result for a single craft (quantity=1)
        base_materials = self._scale_counter(raw_materials, 1 / quantity)
        self.memo[item_id] = base_materials

        visited.remove(item_id)
        return raw_materials

    def calculate_with_steps(self, item_id: str, quantity: float = 1, visited=None) -> Tuple[Counter, List[Dict]]:
        """Like calculate_raw_materials, but also returns the list of production steps.

        Each step has the shape:
        {
          'item': <produced item id>,
          'count': <produced count>,
          'recipe_type': <recipe type string>,
          'ingredients': [ {'item': <ingredient id>, 'count': <needed count>}, ... ]
        }
        """
        # Canonicalize for stable lookups
        item_id = self._canon(item_id)
        if visited is None:
            visited = set()

        # Cycle detection
        if item_id in visited:
            print(f"Warning: Cycle detected at {item_id}. Treating as raw material.")
            return Counter({item_id: quantity}), []

        visited.add(item_id)

        # Base case: If no recipe, it's raw material
        if item_id not in self.recipes:
            visited.remove(item_id)
            return Counter({item_id: quantity}), []

        raw_materials = Counter()
        steps: List[Dict] = []

        recipe = self.recipes[item_id]
        recipe_output_count = self._output_count(recipe)
        crafting_multiplier = quantity / recipe_output_count

        ingredients = self._get_ingredients_from_recipe(recipe)
        # If no parseable ingredients, treat as raw material
        if not ingredients:
            visited.remove(item_id)
            return Counter({item_id: quantity}), []

        # Build current step first (parent-first order)
        current_step_ingredients = []
        for ing in ingredients:
            ing_id = self._canon(ing['item'])
            ing_qty_needed = ing['quantity'] * crafting_multiplier
            current_step_ingredients.append({"item": ing_id, "count": ing_qty_needed})
        steps.append({
            "item": item_id,
            "count": quantity,
            "recipe_type": recipe.get('type', 'unknown'),
            "ingredients": current_step_ingredients,
        })

        # Recurse into ingredients
        for ing in ingredients:
            ing_id = self._canon(ing['item'])
            ing_qty_needed = ing['quantity'] * crafting_multiplier
            sub_raw, sub_steps = self.calculate_with_steps(ing_id, ing_qty_needed, visited.copy())
            raw_materials.update(sub_raw)
            steps.extend(sub_steps)

        visited.remove(item_id)
        return raw_materials, steps

    def _get_ingredients_from_recipe(self, recipe):
        """Extract ingredients structurally for shaped/shapeless-like recipes.

        - Shaped: presence of 'pattern' (list[str]) and 'key' (dict)
        - Shapeless: presence of 'ingredients' (list)
        For choices (arrays), pick the first candidate deterministically.
        Tags are resolved to the first item in the tag list.
        """
        ingredients = []

        def _pick_item(obj: dict):
            # obj may be {'item': 'id'} or {'tag': 'ns:tag'} or dict list entry
            if not isinstance(obj, dict):
                return None
            if 'item' in obj and isinstance(obj['item'], str):
                return obj['item']
            if 'tag' in obj and isinstance(obj['tag'], str):
                lst = self.tags.get(obj['tag'], [])
                return lst[0] if lst else None
            # Some mods use 'items': ['id1','id2']
            if 'items' in obj and isinstance(obj['items'], list) and obj['items']:
                cand = obj['items'][0]
                if isinstance(cand, str):
                    return cand
            return None

        # AE2 Inscriber-like: ingredients is an object with top/middle/bottom
        rtype = recipe.get('type', '') or ''
        if isinstance(recipe.get('ingredients'), dict) and str(rtype).endswith(':inscriber'):
            ingobj = recipe['ingredients']
            for pos in ('top', 'middle', 'bottom'):
                if pos in ingobj and ingobj[pos] is not None:
                    choice = ingobj[pos]
                    if isinstance(choice, list) and choice:
                        choice = choice[0]
                    item_id = _pick_item(choice)
                    if item_id:
                        q = 1
                        if isinstance(choice, dict) and isinstance(choice.get('count'), (int, float)):
                            q = int(choice['count'])
                        ingredients.append({'item': item_id, 'quantity': q})
            return ingredients

        # Shaped-like
        if isinstance(recipe.get('pattern'), list) and isinstance(recipe.get('key'), dict):
            pattern = recipe.get('pattern', [])
            key = recipe.get('key', {})
            chars = "".join([row.replace(" ", "") for row in pattern])
            if chars:
                counts = Counter(chars)
                for ch, cnt in counts.items():
                    if ch in key:
                        cell = key[ch]
                        # cell can be dict or list of dicts
                        choice = None
                        if isinstance(cell, list) and cell:
                            choice = cell[0]
                        elif isinstance(cell, dict):
                            choice = cell
                        item_id = _pick_item(choice) if choice is not None else None
                        if item_id:
                            ingredients.append({'item': item_id, 'quantity': cnt})

        # Shapeless-like
        elif isinstance(recipe.get('ingredients'), list):
            for ing in recipe.get('ingredients', []):
                # ingredient can be dict or list of dicts
                choice = ing[0] if isinstance(ing, list) and ing else ing
                item_id = _pick_item(choice)
                if item_id:
                    q = 1
                    if isinstance(choice, dict) and isinstance(choice.get('count'), (int, float)):
                        q = int(choice['count'])
                    ingredients.append({'item': item_id, 'quantity': q})

        return ingredients

    def _scale_counter(self, counter, factor):
        """Scales all values in a Counter by a factor."""
        return Counter({item: count * factor for item, count in counter.items()})


if __name__ == '__main__':
    instance_path = 'instance'
    print(f"--- Loading data from: {instance_path} ---")
    recipes_data = load_recipes(instance_path)
    tags_data = load_tags(instance_path)

    print("\n--- Initializing BOM Engine ---")
    engine = BomEngine(recipes_data, tags_data)

    target_item = "minecraft:stone_pickaxe"
    target_quantity = 1
    print(f"\n--- Calculating BOM for {target_quantity}x {target_item} ---")

    bom = engine.calculate_raw_materials(target_item, target_quantity)

    print("\n--- Final Raw Material BOM ---")
    print(json.dumps(bom, indent=2))
    # Expected: 3 cobblestone, 2 sticks.
    # 2 sticks -> 2 planks (since recipe makes 4 sticks).
    # 2 planks -> 0.5 logs (since recipe makes 4 planks).
    # Total: 3 cobblestone, 0.5 oak_log.
    # Let's check the math: To get 2 sticks, we need 0.5 of the stick recipe (2/4).
    # The stick recipe needs 2 planks. 0.5 * 2 = 1 plank.
    # To get 1 plank, we need 0.25 of the plank recipe (1/4).
    # The plank recipe needs 1 log. 0.25 * 1 = 0.25 logs.
    # So the expected should be 3 cobblestone, 0.25 oak_log.
    print("\n--- Expected Math Check ---")
    print("To make 1 pickaxe: 3 cobblestone, 2 sticks")
    print("To make 2 sticks: needs 0.5 stick recipe -> 1 plank")
    print("To make 1 plank: needs 0.25 plank recipe -> 0.25 oak_log")
    print("Final expected: {'minecraft:cobblestone': 3.0, 'minecraft:oak_log': 0.25}")
