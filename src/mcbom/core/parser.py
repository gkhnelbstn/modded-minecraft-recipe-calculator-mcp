import os
import json
from pathlib import Path

def load_recipes(base_path: str):
    """
    Loads all recipe .json files from a directory structure like 'data/*/recipes/*.json'.
    For our structure, this is 'instance/*/recipes/*.json'.
    """
    recipes = {}
    root_path = Path(base_path)
    recipe_files = list(root_path.glob('*/recipes/**/*.json'))

    print(f"Parser: Found {len(recipe_files)} recipe files.")

    for file_path in recipe_files:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # The key for the recipe dictionary will be the result item's ID.
            if 'result' in data and 'item' in data['result']:
                recipes[data['result']['item']] = data
    return recipes

def load_tags(base_path: str):
    """
    Loads all item tag .json files from 'instance/*/tags/items/**/*.json'.
    """
    tags = {}
    root_path = Path(base_path)
    tag_files = list(root_path.glob('*/tags/items/**/*.json'))

    print(f"Parser: Found {len(tag_files)} tag files.")

    for file_path in tag_files:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # The key is constructed from the namespace (parent dir) and filename.
            # e.g., instance/minecraft/tags/items/planks.json -> minecraft:planks
            namespace = file_path.parent.parent.parent.name
            tag_name = file_path.stem
            full_tag_name = f"{namespace}:{tag_name}"
            tags[full_tag_name] = data.get('values', [])

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
