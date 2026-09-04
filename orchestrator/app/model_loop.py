"""
Phase: Orchestration / Model Execution
Purpose: Core execution loop managing turn-by-turn prompts and tool responses with target LLM.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from app.schemas.fhir_tools import query_fhir_resource_schema
from app.schemas.auxiliary_tools import auxiliary_tool_schemas
from app.router import route_tool_call
from app.logging.trajectory_logger import TrajectoryLogger

logger = logging.getLogger(__name__)
logger_instance = TrajectoryLogger()

# Assemble all tools for OpenAI function calling
ALL_TOOLS = [query_fhir_resource_schema] + auxiliary_tool_schemas

def _call_llm_api_mock(messages: list, tools: list) -> Dict[str, Any]:
    """
    Simulated LLM response for demonstration.
    In a real implementation, this wraps the `openai.ChatCompletion.create` call
    using the api keys from the environment.
    """
    return {
        "message": {
            "role": "assistant",
            "content": "Based on the mock, I have reached a final clinical decision.",
            "tool_calls": []
        }
    }

def execute_agent_loop(task_id: str, case_context: str, model_provider: str) -> Dict[str, Any]:
    """Execute model evaluation loop for a given case."""
    run_id = str(uuid.uuid4())
    logger.info("Starting model loop for case %s with provider %s (run_id: %s)", task_id, model_provider, run_id)
    
    messages = [
        {"role": "system", "content": "You are a clinical decision-making agent. Use the provided tools to gather data and output a final clinical decision."},
        {"role": "user", "content": f"Case context: {case_context}\nPlease evaluate this case."}
    ]
    
    max_turns = 10
    turns = 0
    
    while turns < max_turns:
        turns += 1
        logger.info("Turn %d for run_id %s", turns, run_id)
        
        # 1. Call LLM (abstracted behind mock for sandbox isolation)
        response = _call_llm_api_mock(messages, ALL_TOOLS)
        message = response.get("message", {})
        
        # 2. Append LLM response to history
        messages.append(message)
        
        # 3. Handle Tool Calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name")
                try:
                    arguments_str = tool_call.get("function", {}).get("arguments", "{}")
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    arguments = {}
                
                # Execute routing via HTTPX
                timestamp = datetime.now(timezone.utc).isoformat()
                tool_response, latency = route_tool_call(tool_name, arguments)
                
                # Log the tool call trajectory
                logger_instance.log_tool_call(run_id, task_id, tool_name, arguments, timestamp, tool_response, latency)
                
                # Feedback tool response to LLM memory
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", "unknown"),
                    "name": tool_name,
                    "content": json.dumps(tool_response)
                })
        else:
            # 4. No tool calls -> Final Answer reached
            final_answer = message.get("content", "")
            timestamp = datetime.now(timezone.utc).isoformat()
            logger_instance.log_final_answer(run_id, task_id, final_answer, timestamp)
            logger.info("Final answer reached for run_id %s", run_id)
            break
            
    if turns >= max_turns:
        logger.warning("Max turns reached for run_id %s without final answer", run_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        logger_instance.log_final_answer(run_id, task_id, "[ERROR: Max Turns Reached]", timestamp)
        
    return {"case_id": task_id, "run_id": run_id, "turns": turns, "status": "completed"}
