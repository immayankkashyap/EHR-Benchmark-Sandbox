"""
Phase: Orchestration / Logging
Purpose: Logger utility to capture full interaction trajectories (prompts, tool calls, outputs) to JSONL.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

class TrajectoryLogger:
    """Logs model trajectory steps to JSONL format."""

    def __init__(self, log_dir: str = "/app/logs"):
        self.log_dir = Path(log_dir)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except IOError as e:
            logger.error("Could not create log directory %s: %s", log_dir, e)
        self.lock = threading.Lock()

    def _append_to_file(self, run_id: str, payload: Dict[str, Any]) -> None:
        """Securely append JSON payload to the specific run trajectory file."""
        log_file = self.log_dir / f"{run_id}.jsonl"
        try:
            with self.lock:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload) + "\n")
        except IOError as e:
            logger.error("Failed to write to trajectory log %s: %s", log_file, e)

    def log_tool_call(
        self,
        run_id: str,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timestamp: str,
        raw_response: Any,
        latency_ms: float
    ) -> None:
        """Log a tool invocation step."""
        payload = {
            "type": "tool_call",
            "run_id": run_id,
            "task_id": task_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "timestamp": timestamp,
            "raw_response": raw_response,
            "latency_ms": latency_ms
        }
        self._append_to_file(run_id, payload)

    def log_final_answer(self, run_id: str, task_id: str, answer: str, timestamp: str) -> None:
        """Log the final answer returned by the LLM."""
        payload = {
            "type": "final_answer",
            "run_id": run_id,
            "task_id": task_id,
            "answer": answer,
            "timestamp": timestamp
        }
        self._append_to_file(run_id, payload)
