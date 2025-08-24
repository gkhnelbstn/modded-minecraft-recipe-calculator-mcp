from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from celery.result import AsyncResult

from mcbom.worker.tasks import calculate_bom_task
from mcbom.llm.client import extract_targets_from_text
from mcbom.llm.schemas import ExtractedPlan

# --- Application Setup ---
app = FastAPI(
    title="MC-BOM API",
    description="API for calculating Minecraft Bill of Materials.",
    version="0.2.0-async"
)

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
