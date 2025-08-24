import os
import sys
import json
import argparse
from typing import Optional

from mcbom.core.parser import load_recipes, load_tags
from mcbom.core.engine import BomEngine
from mcbom.core.exporter import to_json, to_mermaid


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="craftcost",
        description="Calculate total raw materials and steps for a target Minecraft item from datapack recipes.",
    )
    parser.add_argument(
        "item",
        help="Target item id (e.g., 'minecraft:stick' or 'appliedenergistics2:controller')",
    )
    qty_group = parser.add_mutually_exclusive_group()
    qty_group.add_argument(
        "-n", "--quantity",
        type=int,
        default=1,
        help="Target quantity (default: 1)",
    )
    qty_group.add_argument(
        "--cube",
        type=int,
        help="If provided, calculates quantity as N^3 (e.g., 3 -> 27)",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help="Also output a Mermaid flowchart after JSON output",
    )
    parser.add_argument(
        "--datapack-path",
        default=os.environ.get("ATM10_PATH", "instance"),
        help="Base path to datapack/instance directory (default: env ATM10_PATH or 'instance')",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write JSON output to a file instead of stdout",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    quantity = (args.cube ** 3) if args.cube else args.quantity

    # Load data
    recipes = load_recipes(args.datapack_path)
    tags = load_tags(args.datapack_path)

    engine = BomEngine(recipes, tags)
    analysis = engine.analyze(args.item, quantity)

    json_str = to_json(analysis)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
    else:
        print(json_str)

    if args.diagram:
        diagram = to_mermaid(analysis)
        # Separate blocks for readability when printing both
        if not args.output:
            print("\n---\n")
        print(diagram)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
