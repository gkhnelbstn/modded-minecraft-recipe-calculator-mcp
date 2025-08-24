import json
from collections import Counter
from mcbom.core.parser import load_recipes, load_tags
from typing import List, Dict, Tuple
 
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
        recipe_output_count = recipe.get('result', {}).get('count', 1)
        crafting_multiplier = quantity / recipe_output_count

        ingredients = self._get_ingredients_from_recipe(recipe)

        for ingredient in ingredients:
            ingredient_id = ingredient['item']
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
        recipe_output_count = recipe.get('result', {}).get('count', 1)
        crafting_multiplier = quantity / recipe_output_count

        ingredients = self._get_ingredients_from_recipe(recipe)

        # Build current step first (parent-first order)
        current_step_ingredients = []
        for ing in ingredients:
            ing_id = ing['item']
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
            ing_id = ing['item']
            ing_qty_needed = ing['quantity'] * crafting_multiplier
            sub_raw, sub_steps = self.calculate_with_steps(ing_id, ing_qty_needed, visited.copy())
            raw_materials.update(sub_raw)
            steps.extend(sub_steps)

        visited.remove(item_id)
        return raw_materials, steps

    def _get_ingredients_from_recipe(self, recipe):
        """Helper to extract a simple ingredient list from different recipe types."""
        ingredients = []
        if recipe.get('type') == 'minecraft:crafting_shaped':
            pattern = recipe.get('pattern', [])
            key = recipe.get('key', {})
            ingredient_counts = Counter("".join(pattern).replace(" ", ""))
            for char, count in ingredient_counts.items():
                if char in key:
                    item_info = key[char]
                    # For PoC, resolve tag to its first item
                    if 'tag' in item_info:
                        tag_items = self.tags.get(item_info['tag'], [])
                        if tag_items:
                            ingredients.append({'item': tag_items[0], 'quantity': count})
                    else:
                        ingredients.append({'item': item_info['item'], 'quantity': count})
        elif recipe.get('type') == 'minecraft:crafting_shapeless':
            for ing in recipe.get('ingredients', []):
                 if 'tag' in ing:
                    tag_items = self.tags.get(ing['tag'], [])
                    if tag_items:
                        ingredients.append({'item': tag_items[0], 'quantity': 1})
                 else:
                    ingredients.append({'item': ing['item'], 'quantity': 1})
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
