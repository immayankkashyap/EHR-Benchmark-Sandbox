"""
Phase: Case Ingestion
Purpose: Ingest patient case specifications and convert/upload them as FHIR resources into the HAPI FHIR server.
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

FHIR_BASE_URL = "http://localhost:8080/fhir"

def create_meta_tag(task_id: str) -> Dict[str, Any]:
    """Generate the meta.tag block for FHIR resources."""
    return {
        "meta": {
            "tag": [
                {
                    "system": "http://healthcare-ehr-sandbox.local/tags/task_id",
                    "code": task_id
                }
            ]
        }
    }

def check_existing_resources(task_id: str) -> bool:
    """Check if resources with the given task_id already exist in the FHIR server."""
    url = f"{FHIR_BASE_URL}/Patient"
    params = {"_tag": task_id}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("total", 0) > 0 or len(data.get("entry", [])) > 0:
            return True
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to query FHIR server: {e}")
        sys.exit(1)

def construct_patient(patient_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """Construct a FHIR Patient resource."""
    resource = {
        "resourceType": "Patient",
        "id": patient_data.get("id", "patient-1"),
        **create_meta_tag(task_id),
        "name": [
            {
                "family": patient_data["name"]["last_name"],
                "given": [patient_data["name"]["first_name"]]
            }
        ],
        "gender": patient_data.get("gender", "unknown"),
        "birthDate": patient_data.get("birthDate", "")
    }
    return resource

def construct_condition(cond_data: Dict[str, Any], patient_id: str, task_id: str) -> Dict[str, Any]:
    """Construct a FHIR Condition resource."""
    resource = {
        "resourceType": "Condition",
        "id": cond_data.get("id"),
        **create_meta_tag(task_id),
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": cond_data.get("clinical_status", "active")
                }
            ]
        },
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": cond_data.get("code"),
                    "display": cond_data.get("display")
                }
            ]
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "recordedDate": cond_data.get("recorded_date")
    }
    return resource

def construct_observation(obs_data: Dict[str, Any], patient_id: str, task_id: str) -> Dict[str, Any]:
    """Construct a FHIR Observation resource."""
    resource = {
        "resourceType": "Observation",
        "id": obs_data.get("id"),
        **create_meta_tag(task_id),
        "status": obs_data.get("status", "final"),
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": obs_data.get("code"),
                    "display": obs_data.get("display")
                }
            ]
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "effectiveDateTime": obs_data.get("effective_date_time")
    }
    
    if "value" in obs_data:
        resource["valueQuantity"] = {
            "value": obs_data["value"],
            "unit": obs_data.get("unit"),
            "system": "http://unitsofmeasure.org",
            "code": obs_data.get("unit")
        }
        
    if "components" in obs_data:
        components = []
        for comp in obs_data["components"]:
            components.append({
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": comp.get("code"),
                            "display": comp.get("display")
                        }
                    ]
                },
                "valueQuantity": {
                    "value": comp["value"],
                    "unit": comp.get("unit"),
                    "system": "http://unitsofmeasure.org",
                    "code": comp.get("unit")
                }
            })
        resource["component"] = components
        
    return resource

def construct_medication_request(med_data: Dict[str, Any], patient_id: str, task_id: str) -> Dict[str, Any]:
    """Construct a FHIR MedicationRequest resource."""
    resource = {
        "resourceType": "MedicationRequest",
        "id": med_data.get("id"),
        **create_meta_tag(task_id),
        "status": med_data.get("status", "active"),
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": med_data.get("code"),
                    "display": med_data.get("display")
                }
            ]
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "authoredOn": med_data.get("authored_on")
    }
    return resource

def construct_allergy_intolerance(allergy_data: Dict[str, Any], patient_id: str, task_id: str) -> Dict[str, Any]:
    """Construct a FHIR AllergyIntolerance resource."""
    resource = {
        "resourceType": "AllergyIntolerance",
        "id": allergy_data.get("id"),
        **create_meta_tag(task_id),
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                    "code": allergy_data.get("clinical_status", "active")
                }
            ]
        },
        "code": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "display": allergy_data.get("substance")
                }
            ]
        },
        "patient": {
            "reference": f"Patient/{patient_id}"
        }
    }
    return resource

def construct_transaction_bundle(case_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Construct a FHIR Transaction Bundle from the case spec."""
    task_id = case_spec["metadata"]["task_id"]
    patient_data = case_spec["patient"]
    patient_id = patient_data.get("id", "patient-1")
    
    entries = []
    
    # 1. Add Patient
    patient_resource = construct_patient(patient_data, task_id)
    entries.append({
        "resource": patient_resource,
        "request": {
            "method": "PUT",
            "url": f"Patient/{patient_id}"
        }
    })
    
    # 2. Add Conditions
    for cond in case_spec.get("conditions", []):
        entries.append({
            "resource": construct_condition(cond, patient_id, task_id),
            "request": {
                "method": "POST",
                "url": "Condition"
            }
        })
        
    # 3. Add Observations
    for obs in case_spec.get("observations", []):
        entries.append({
            "resource": construct_observation(obs, patient_id, task_id),
            "request": {
                "method": "POST",
                "url": "Observation"
            }
        })
        
    # 4. Add Medications (MedicationRequest)
    for med in case_spec.get("medications", []):
        entries.append({
            "resource": construct_medication_request(med, patient_id, task_id),
            "request": {
                "method": "POST",
                "url": "MedicationRequest"
            }
        })
        
    # 5. Add Allergies (AllergyIntolerance)
    for allergy in case_spec.get("allergies", []):
        entries.append({
            "resource": construct_allergy_intolerance(allergy, patient_id, task_id),
            "request": {
                "method": "POST",
                "url": "AllergyIntolerance"
            }
        })
        
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries
    }
    return bundle

def ingest_case(file_path: str) -> None:
    """Read case spec JSON, check idempotency, construct bundle, and POST to FHIR server."""
    logger.info(f"Loading case specification from {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            case_spec = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read or parse JSON file: {e}")
        sys.exit(1)
        
    try:
        task_id = case_spec["metadata"]["task_id"]
    except KeyError:
        logger.error("JSON is missing metadata.task_id")
        sys.exit(1)
        
    logger.info(f"Checking existing resources for task_id: {task_id}")
    if check_existing_resources(task_id):
        logger.error(f"Resources for task_id '{task_id}' already exist. Aborting to prevent duplicates.")
        sys.exit(1)
        
    logger.info(f"Constructing FHIR Transaction Bundle for {task_id}")
    bundle = construct_transaction_bundle(case_spec)
    
    logger.info("POSTing Transaction Bundle to FHIR Server...")
    try:
        response = requests.post(
            FHIR_BASE_URL, 
            json=bundle, 
            headers={"Content-Type": "application/json"}, 
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"Successfully ingested case {task_id}. Response Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to POST transaction bundle: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response Body: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest patient case specifications into FHIR store.")
    parser.add_argument("file_path", type=str, help="Path to the case specification JSON file.")
    args = parser.parse_args()
    
    ingest_case(args.file_path)
