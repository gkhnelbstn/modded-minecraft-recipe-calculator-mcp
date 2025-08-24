import json
from mcbom.llm.schemas import ExtractedPlan

def get_llm_prompt(user_text, prefer_ns):
    """
    Constructs the prompt for the LLM based on the user's template.
    """
    # This is a simplified version of the user's prompt template.
    prompt = f"""
SYSTEM: You are a Minecraft modding planner. Extract exact items and counts.
USER: {user_text}
CONTEXT:
- Prefer namespaces (order): {prefer_ns}
- Instance recipe & tags will be read locally; do NOT invent items.
- If the request asks for a cube of a block, qty = N^3.
OUTPUT JSON SCHEMA:
{{ "targets":[{{ "item":"ns:item", "qty":int, "qtyCube":int|null }}],
  "notes":[string], "warnings":[string] }}
"""
    return prompt

def extract_targets_from_text(user_text: str, prefer_ns: list = None):
    """
    (Mocked) Simulates a call to an LLM to extract a structured plan
    from free-form user text.
    """
    if prefer_ns is None:
        prefer_ns = ["ae2", "minecraft"]

    prompt = get_llm_prompt(user_text, prefer_ns)
    print("--- Generated LLM Prompt ---")
    print(prompt)

    # --- MOCK LLM CALL ---
    # In a real app, you would call the Gemini API here.
    # We are hardcoding the response to simulate the LLM's output.
    print("\n--- Mocked LLM Response ---")
    if "5x5x5 küp" in user_text:
        mock_response_str = """
        {
          "targets": [
            {"item": "ae2:controller", "qty": 1, "qtyCube": 5},
            {"item": "ae2:me_drive", "qty": 1},
            {"item": "ae2:dense_cable", "qty": 32}
          ],
          "notes": ["User wants a 5x5x5 cube of controllers.", "Also needs drives and cables."],
          "warnings": ["dense_cable has no color specified, assuming default."]
        }
        """
    else:
        mock_response_str = """
        {
          "targets": [{"item": "minecraft:stone_pickaxe", "qty": 1}],
          "warnings": ["Query was not specific, defaulting to stone pickaxe."]
        }
        """
    print(mock_response_str)

    # --- VALIDATE SCHEMA ---
    # This step is crucial, as the user requested.
    try:
        response_data = json.loads(mock_response_str)
        validated_plan = ExtractedPlan.model_validate(response_data)
        print("\n--- LLM Response Schema Validated Successfully ---")
        return validated_plan.model_dump() # Return as a dictionary
    except Exception as e:
        print(f"ERROR: LLM response failed validation: {e}")
        return {"error": "LLM response was not in the expected format."}


if __name__ == '__main__':
    test_query = "AE2 controller’dan 5x5x5 küp kuracağım; ayrıca bir ME Drive ve 32 dense cable lazım."
    plan = extract_targets_from_text(test_query)
    print("\n--- Final Structured Plan ---")
    print(json.dumps(plan, indent=2))
