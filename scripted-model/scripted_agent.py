"""
Phase: E2E Verification / Scripted Model
Purpose: Deterministic agent mocking an LLM's OpenAI API response trajectory.
"""

import json
import logging
import uuid
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class ScriptedAgent:
    """Mock state machine generating predefined tool calls and final answers."""

    def __init__(self):
        pass

    def generate_next_turn(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Examine conversation history length to determine the deterministic next step."""
        
        # Count previous assistant messages to determine the current 'turn' state
        assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")
        
        logger.info("ScriptedAgent generating turn %d based on message history.", assistant_turns + 1)

        # State 0 (Turn 1): Return query_fhir_resource for Condition
        if assistant_turns == 0:
            return {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": "query_fhir_resource",
                                "arguments": json.dumps({
                                    "resource_type": "Condition",
                                    "search_parameters": {"subject": "Patient/MEDMCQA-CASE-001"}
                                })
                            }
                        }
                    ]
                }
            }
            
        # State 1 (Turn 2): Return get_dosage_guideline for Morphine
        elif assistant_turns == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": "get_dosage_guideline",
                                "arguments": json.dumps({
                                    "drug": "Morphine",
                                    "indication": "pain",
                                    "weight_kg": 70
                                })
                            }
                        }
                    ]
                }
            }
            
        # State 2 (Turn 3): Return final answer
        else:
            return {
                "message": {
                    "role": "assistant",
                    "content": "Administer Morphine 10mg IV.",
                    "tool_calls": []
                }
            }
