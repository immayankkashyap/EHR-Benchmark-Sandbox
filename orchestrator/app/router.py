"""
Phase: Orchestration / Routing
Purpose: Router component to forward model tool invocations to FHIR or auxiliary microservices.
"""

import logging
import time
from typing import Any, Dict, Tuple

import httpx

logger = logging.getLogger(__name__)

# Internal Network Endpoint Mappings
SERVICE_URLS = {
    "query_fhir_resource": "http://hapi-fhir-jpaserver:8080/fhir",
    "check_drug_interaction": "http://drug-interaction-checker:8000/check-interaction",
    "lookup_lab_range": "http://lab-reference-range:8000/lab-range",
    "get_dosage_guideline": "http://dosage-guideline:8000/dosage"
}

def _handle_fhir_query(url: str, arguments: Dict[str, Any]) -> Tuple[Any, float]:
    """Specific handler for FHIR queries since they route differently from RPCs."""
    resource_type = arguments.get("resource_type", "")
    search_params = arguments.get("search_parameters", {})
    
    target_url = f"{url}/{resource_type}"
    start_time = time.time()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(target_url, params=search_params)
            response.raise_for_status()
            data = response.json()
            latency_ms = (time.time() - start_time) * 1000
            return data, latency_ms
    except httpx.HTTPStatusError as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"error": f"HTTP {e.response.status_code} Error: {e.response.text}"}, latency_ms
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"error": f"Failed to connect to FHIR server: {str(e)}"}, latency_ms

def _handle_auxiliary_query(url: str, arguments: Dict[str, Any]) -> Tuple[Any, float]:
    """Generic handler for auxiliary tools that expect GET query parameters."""
    start_time = time.time()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=arguments)
            # We specifically catch 404/422 as expected application errors from our APIs
            if response.status_code in (404, 422):
                latency_ms = (time.time() - start_time) * 1000
                return response.json(), latency_ms
            
            response.raise_for_status()
            latency_ms = (time.time() - start_time) * 1000
            return response.json(), latency_ms
    except httpx.HTTPStatusError as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"error": f"Unexpected HTTP error {e.response.status_code}"}, latency_ms
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"error": f"Failed to communicate with service: {str(e)}"}, latency_ms

def route_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, float]:
    """
    Route tool invocation to appropriate internal service.
    Returns:
        (response_data, latency_ms)
    """
    logger.info("Routing tool call: %s", tool_name)
    
    if tool_name not in SERVICE_URLS:
        return {"error": f"Unknown tool: {tool_name}"}, 0.0
        
    url = SERVICE_URLS[tool_name]
    
    if tool_name == "query_fhir_resource":
        return _handle_fhir_query(url, arguments)
    else:
        return _handle_auxiliary_query(url, arguments)
