"""
Phase: Baseline Evaluation / Scripted Model
Purpose: Deterministic agent runner that executes pre-recorded tool calls from YAML action scripts.
"""

import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

class ScriptedAgent:
    """Scripted baseline agent for deterministic sandbox verification."""

    def __init__(self, script_path: str):
        self.script_path = Path(script_path)

    def run(self):
        """Execute pre-scripted steps."""
        logger.info("Executing scripted agent steps from %s", self.script_path)
        if self.script_path.exists():
            with open(self.script_path, "r", encoding="utf-8") as f:
                steps = yaml.safe_load(f)
            return steps
        return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ScriptedAgent("scripted-model/scripts/dry_run_case_001.yaml")
    agent.run()
