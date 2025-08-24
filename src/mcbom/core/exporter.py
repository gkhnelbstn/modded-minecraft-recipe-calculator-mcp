import json

def to_json(bom_data: dict):
    """
    Exports the given BOM data to a JSON string.

    Args:
        bom_data: The dictionary containing the bill of materials.

    Returns:
        A JSON formatted string.
    """
    return json.dumps(bom_data, indent=2)

def to_mermaid(bom_data: dict):
    """

    Exports the given BOM data to a Mermaid.js flowchart string.
    (This will be implemented in a later phase).

    """
    # Placeholder for future implementation
    return "flowchart TD\n  A[Raw Materials] --> B[Final Item]"
