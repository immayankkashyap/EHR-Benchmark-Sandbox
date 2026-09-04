"""
Phase: Orchestration
Purpose: Main service entrypoint for the EHR Benchmark Orchestrator managing model evaluation runs.
"""

from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

from app.model_loop import execute_agent_loop

app = FastAPI(title="EHR Benchmark Orchestrator", version="1.0.0")

class RunTaskRequest(BaseModel):
    task_id: str
    model_provider: str
    patient_id: str
    case_context: str = ""

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "orchestrator"}

@app.post("/run-task")
async def run_task(request: RunTaskRequest, background_tasks: BackgroundTasks):
    """Trigger evaluation run for a specific case ID in the background."""
    
    context = request.case_context or f"Evaluate clinical case for patient {request.patient_id} associated with task {request.task_id}."
    
    background_tasks.add_task(
        execute_agent_loop,
        task_id=request.task_id,
        case_context=context,
        model_provider=request.model_provider
    )
    
    return {
        "message": "Task execution initiated in background.",
        "task_id": request.task_id,
        "patient_id": request.patient_id,
        "model_provider": request.model_provider
    }
