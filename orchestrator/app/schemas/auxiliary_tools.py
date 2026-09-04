"""
Phase: Orchestration / Schemas
Purpose: Pydantic schemas and tool definitions for auxiliary clinical microservice tools.
"""

from typing import Any, Dict, List

auxiliary_tool_schemas: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_drug_interaction",
            "description": "Check for known clinical interactions between two drugs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug_a": {
                        "type": "string",
                        "description": "Name of the first drug."
                    },
                    "drug_b": {
                        "type": "string",
                        "description": "Name of the second drug."
                    }
                },
                "required": ["drug_a", "drug_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_lab_range",
            "description": "Lookup the standard reference range for a laboratory test based on patient demographics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test": {
                        "type": "string",
                        "description": "Name or alias of the lab test."
                    },
                    "age": {
                        "type": "integer",
                        "description": "Age of the patient in years."
                    },
                    "sex": {
                        "type": "string",
                        "description": "Biological sex of the patient ('male', 'female', or 'all')."
                    }
                },
                "required": ["test", "age", "sex"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dosage_guideline",
            "description": "Retrieve dosing guidelines for a medication.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drug": {
                        "type": "string",
                        "description": "Name of the medication."
                    },
                    "indication": {
                        "type": "string",
                        "description": "Clinical indication for the drug."
                    },
                    "weight_kg": {
                        "type": "number",
                        "description": "Patient weight in kilograms."
                    }
                },
                "required": ["drug"]
            }
        }
    }
]
