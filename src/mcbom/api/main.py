import os
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from celery.result import AsyncResult
from typing import Optional
from mcbom.worker.tasks import calculate_bom_task
from mcbom.llm.client import extract_targets_from_text
from mcbom.llm.schemas import ExtractedPlan
from mcbom.core.engine import BomEngine
from mcbom.core.parser import load_recipes, load_tags
from mcbom.core.exporter import to_mermaid
from mcbom.core.indexer import (
    query_items as idx_query_items,
    build_index as idx_build_index,
)

# TODO(roadmap-api):
# - Upload endpoint to ingest JEI/RecipeManager dump files and merge into runtime registry.
# - Config endpoint to control preferences (recipe types order, tag strategies).
# - Streaming progress or SSE for long calculations; optional async route parity.
# - Structured logging and correlation IDs; replace prints with logger.
# - Authentication/rate limiting hooks for multi-user deployment.

# --- Application Setup ---
app = FastAPI(
    title="MC-BOM API",
    description="API for calculating Minecraft Bill of Materials.",
    version="0.2.0-async"
)

# Allow local UI and other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve minimal static UI from /ui
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")

# Warm up the items index on startup (best-effort)
@app.on_event("startup")
async def _warm_items_index() -> None:
    base = os.environ.get("MCBOM_DATA_ROOT", "/data/instance")
    try:
        idx_build_index(base, refresh=False)
        print(f"API: warmed items index for base '{base}'")
    except Exception as e:
        # Do not block startup on indexing issues
        print(f"API: items index warmup skipped: {e}")

# --- Data Models ---
class PlanRequest(BaseModel):
    plan_text: str
    prefer_ns: list[str] = ["ae2", "minecraft"]

class BomRequest(BaseModel):
    item_id: str
    quantity: int = 1
    instance_path: str = "instance"

class TaskResponse(BaseModel):
    task_id: str
    status: str

class ResultResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None

class DirectCalcRequest(BaseModel):
    """Synchronous calculation request without Celery.

    Args:
        item_id: Fully-qualified item id (e.g., 'minecraft:stick').
        quantity: Target quantity.
        instance_path: Base path inside container/host where datapack data resides.
        diagram: Whether to include Mermaid string in the response.
    """
    item_id: str
    quantity: int = 1
    instance_path: Optional[str] = None
    diagram: bool = False

# --- API Endpoints ---
@app.post("/plan", response_model=ExtractedPlan)
async def create_plan_from_text(request: PlanRequest):
    """
    Takes a user's natural language plan and uses the LLM interface
    to convert it into a structured list of target items.
    """
    print(f"API: Received /plan request with text: '{request.plan_text}'")
    structured_plan = extract_targets_from_text(request.plan_text, request.prefer_ns)
    return structured_plan


@app.post("/bom", response_model=TaskResponse, status_code=202)
async def create_bom_calculation_task(request: BomRequest):
    """
    Accepts a BOM request and submits it as a background task to the worker.
    """
    print(f"API: Submitting BOM task for {request.quantity}x {request.item_id}")
    task = calculate_bom_task.delay(
        item_id=request.item_id,
        quantity=request.quantity,
        instance_path=request.instance_path
    )
    return TaskResponse(task_id=task.id, status="SUBMITTED")

@app.get("/results/{task_id}", response_model=ResultResponse)
async def get_task_result(task_id: str):
    """
    Retrieves the status and result of a submitted task.
    """
    task_result = AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }

    return JSONResponse(response)

@app.post("/calculate")
async def calculate_bom_direct(req: DirectCalcRequest):
    """Synchronously calculates a BOM using on-disk datapacks and mod JARs.

    It reads recipes/tags via parser, runs BomEngine.analyze, and optionally
    returns a Mermaid diagram string.
    """
    base_path = req.instance_path or os.environ.get("MCBOM_DATA_ROOT", "/data/instance")
    print(f"API: /calculate -> {req.quantity}x {req.item_id} using base '{base_path}'")

    recipes = load_recipes(base_path)
    tags = load_tags(base_path)
    engine = BomEngine(recipes, tags)
    analysis = engine.analyze(req.item_id, req.quantity)

    resp = {"analysis": analysis}
    if req.diagram:
        resp["mermaid"] = to_mermaid(analysis)
    return JSONResponse(resp)

@app.get("/items")
async def list_items(
    query: Optional[str] = None,
    limit: int = 50,
    instance_path: Optional[str] = None,
    refresh: bool = False,
):
    """Return items from a persistent SQLite index for fast search.

    Query Params:
      - query: optional search text; tokenized prefix search when FTS is available, else LIKE.
      - limit: max results, clamped to [1, 500].
      - instance_path: override for data root; defaults to env MCBOM_DATA_ROOT or /data/instance.
      - refresh: force rebuild of the index before querying.
    """
    base = instance_path or os.environ.get("MCBOM_DATA_ROOT", "/data/instance")
    limit = max(1, min(limit, 500))
    print(f"API: /items -> base '{base}', query='{query}', limit={limit}, refresh={refresh}")

    items = idx_query_items(base, query, limit=limit, refresh=refresh)
    return JSONResponse({"items": items, "count": len(items)})
