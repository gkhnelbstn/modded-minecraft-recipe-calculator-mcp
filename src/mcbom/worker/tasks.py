from mcbom.worker.celery_app import celery_app
from mcbom.core.parser import load_recipes, load_tags
from mcbom.core.engine import BomEngine

@celery_app.task(name="create_bom_task")
def calculate_bom_task(item_id: str, quantity: int, instance_path: str) -> dict:
    """
    A Celery task to perform the heavy computation of calculating a BOM.
    """
    print(f"WORKER: Starting BOM calculation for {quantity}x {item_id}")

    try:
        # This is the same logic from the old synchronous endpoint
        recipes = load_recipes(instance_path)
        tags = load_tags(instance_path)

        engine = BomEngine(recipes, tags)

        raw_materials_bom = engine.calculate_raw_materials(item_id, quantity)

        print(f"WORKER: Calculation finished for {item_id}. Found {len(raw_materials_bom)} raw materials.")
        # Celery needs serializable results, a dict is perfect.
        return dict(raw_materials_bom)
    except Exception as e:
        print(f"WORKER: Error during calculation for {item_id}: {e}")
        # Propagate error information
        return {"error": str(e)}
