import json
from typing import Dict, List, Tuple

def to_json(bom_data: dict):
    """
    Exports the given BOM data to a JSON string.

    Args:
        bom_data: The dictionary containing the bill of materials.

    Returns:
        A JSON formatted string.
    """
    return json.dumps(bom_data, indent=2)

def to_mermaid(analysis: Dict) -> str:
    """Converts analyzer output into a Mermaid flowchart string.

    The expected input structure is the dict returned by BomEngine.analyze:
    {
      'target': str,
      'quantity': int,
      'total_raw_materials': [ {'item': str, 'count': number}, ... ],
      'steps': [
          {
            'item': str, 'count': number, 'recipe_type': str,
            'ingredients': [ {'item': str, 'count': number}, ... ]
          }, ...
      ]
    }
    """
    steps: List[Dict] = analysis.get("steps", [])

    # Collect unique items to define nodes
    items: List[str] = []
    def ensure_item(it: str):
        if it not in items:
            items.append(it)

    for step in steps:
        ensure_item(step["item"])
        for ing in step.get("ingredients", []):
            ensure_item(ing["item"])

    # Assign node IDs
    id_map: Dict[str, str] = {it: f"n{i+1}" for i, it in enumerate(items)}

    def fmt_qty(v: float) -> str:
        # Render integers without .0; small floats to 4 decimals
        if isinstance(v, int):
            return str(v)
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:.4f}".rstrip("0").rstrip(".")

    def esc_label(s: str) -> str:
        # Basic escaping for quotes in Mermaid labels
        return s.replace("\"", "'")

    lines: List[str] = ["flowchart LR"]

    # Node declarations with labels as just the item id; optional counts will be on edges
    for it in items:
        node_id = id_map[it]
        label = esc_label(it)
        lines.append(f"  {node_id}[\"{label}\"]")

    # Edges per step: ingredient -- x<count> --> product
    for step in steps:
        out_id = id_map[step["item"]]
        for ing in step.get("ingredients", []):
            in_id = id_map[ing["item"]]
            qty = fmt_qty(ing["count"])
            lines.append(f"  {in_id} -- x{qty} --> {out_id}")

    return "\n".join(lines)
