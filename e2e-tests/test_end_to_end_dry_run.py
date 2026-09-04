"""
Phase: E2E Verification
Purpose: Automated deterministic End-to-End dry run to validate network topologies, tool routing, 
         and logging functionality without using live LLM API keys.
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = "http://localhost:8000/run-task"
LOG_DIR = Path("./logs")

def setup_environment():
    """Reset sandbox environment using the reset shell script."""
    logger.info("Executing environment reset (this may take a minute)...")
    try:
        subprocess.run(["bash", "scripts/reset_and_run.sh"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Environment reset failed with exit code %s", e.returncode)
        raise RuntimeError("Sandbox reset failed.") from e
    logger.info("Environment reset and case ingestion successful.")

def trigger_evaluation(task_id: str) -> str:
    """Trigger the evaluation task via Orchestrator API."""
    logger.info("Triggering orchestrator evaluation for task %s using scripted_agent.", task_id)
    payload = {
        "task_id": task_id,
        "model_provider": "scripted_agent",
        "patient_id": "MEDMCQA-CASE-001",
        "case_context": "Patient presents with abdominal pain. Evaluate condition and output Morphine dosage."
    }
    
    with httpx.Client(timeout=10.0) as client:
        response = client.post(ORCHESTRATOR_URL, json=payload)
        response.raise_for_status()
        
    logger.info("Orchestrator accepted the task.")
    return "trigger_success"

def wait_for_trajectory_log() -> Path:
    """Poll the logs directory for the newest jsonl file representing our run."""
    logger.info("Waiting for trajectory log file generation...")
    
    max_wait = 45
    elapsed = 0
    
    while elapsed < max_wait:
        # Get latest jsonl file in logs
        files = list(LOG_DIR.glob("*.jsonl"))
        if files:
            latest_file = max(files, key=os.path.getmtime)
            
            with open(latest_file, "r") as f:
                content = f.read()
                if "final_answer" in content:
                    logger.info("Found completed trajectory log: %s", latest_file.name)
                    return latest_file
        
        time.sleep(2)
        elapsed += 2
        
    raise TimeoutError("Timed out waiting for the trajectory log to complete.")

def test_deterministic_e2e_dry_run():
    """Main E2E test function executed by pytest."""
    
    logger.info("=== STARTING DETERMINISTIC E2E DRY RUN ===")
    
    # Step 1: Execute Reset and Run
    setup_environment()
    
    # Step 2: Fire HTTP POST to Orchestrator
    trigger_evaluation(task_id="MEDMCQA-CASE-001")
    
    # Step 3 & 4: Poll and retrieve the generated log
    log_file = wait_for_trajectory_log()
    
    # Step 5: Parse and assert JSONL contents
    logger.info("Validating trajectory events...")
    events = []
    with open(log_file, "r") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
                
    assert len(events) == 3, f"Expected 3 events (2 tool calls, 1 final answer), got {len(events)}"
    
    # Assert Event 1: Tool Call 1
    assert events[0]["type"] == "tool_call"
    assert events[0]["tool_name"] == "query_fhir_resource"
    assert "Condition" in json.dumps(events[0]["arguments"])
    assert events[0]["latency_ms"] > 0
    logger.info("Event 1 (FHIR Query) Validation: PASS")
    
    # Assert Event 2: Tool Call 2
    assert events[1]["type"] == "tool_call"
    assert events[1]["tool_name"] == "get_dosage_guideline"
    assert "Morphine" in json.dumps(events[1]["arguments"])
    assert events[1]["latency_ms"] > 0
    logger.info("Event 2 (Dosage Guideline) Validation: PASS")
    
    # Assert Event 3: Final Answer
    assert events[2]["type"] == "final_answer"
    assert "10mg" in events[2]["answer"]
    logger.info("Event 3 (Final Answer) Validation: PASS")
    
    logger.info("=== DETERMINISTIC E2E DRY RUN COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_deterministic_e2e_dry_run()
