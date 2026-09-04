"""
Phase: Orchestration / Schemas
Purpose: Pydantic schemas and tool definitions for FHIR API interactions by the evaluation model.
"""

from typing import Any, Dict

query_fhir_resource_schema: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_fhir_resource",
        "description": "Query the FHIR database for patient clinical resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "The FHIR resource type to query (e.g., 'Patient', 'Condition', 'Observation', 'MedicationRequest', 'AllergyIntolerance')."
                },
                "search_parameters": {
                    "type": "object",
                    "description": "Key-value pairs for the FHIR search query URL parameters (e.g., {'subject': 'Patient/123', 'status': 'final'}).",
                    "additionalProperties": True
                }
            },
            "required": ["resource_type", "search_parameters"]
        }
    }
}
