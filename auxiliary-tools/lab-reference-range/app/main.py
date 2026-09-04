"""
Phase: Auxiliary Tools - Lab Reference Range
Purpose: Service entrypoint providing API endpoints to look up standard laboratory test reference ranges.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from contextlib import asynccontextmanager

SOURCE_VERSION = "v2026-09-04"

# Pydantic Schemas
class LabRangeDetails(BaseModel):
    test: str
    age_min: int
    age_max: int
    sex: str
    range_low: float
    range_high: float
    unit: str

class LabRangeResponse(BaseModel):
    result: LabRangeDetails
    source_version: str
    timestamp: str

# Data Store
lab_ranges_db: List[Dict[str, Any]] = []

def load_data():
    """Load lab ranges data into memory."""
    global lab_ranges_db
    data_path = Path(__file__).parent / "data" / f"lab_ranges_{SOURCE_VERSION}.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            lab_ranges_db = json.load(f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    yield

app = FastAPI(title="Lab Reference Range Service", version="1.0.0", lifespan=lifespan)

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "lab-reference-range"}

@app.get("/lab-range", response_model=LabRangeResponse)
def get_lab_range(
    test: str = Query(..., description="Name or alias of the lab test"),
    age: int = Query(..., description="Age of the patient in years"),
    sex: str = Query(..., description="Biological sex of the patient (male/female/all)")
):
    """Retrieve reference range for a specific test based on demographic parameters."""
    test_query = test.lower().strip()
    sex_query = sex.lower().strip()

    for entry in lab_ranges_db:
        # Match test name or alias
        matches_test = test_query == entry["test"].lower() or any(test_query == alias.lower() for alias in entry.get("aliases", []))
        
        # Match age
        matches_age = entry["age_min"] <= age <= entry["age_max"]
        
        # Match sex
        matches_sex = entry["sex"] == "all" or entry["sex"] == sex_query
        
        if matches_test and matches_age and matches_sex:
            details = LabRangeDetails(
                test=entry["test"],
                age_min=entry["age_min"],
                age_max=entry["age_max"],
                sex=entry["sex"],
                range_low=entry["range_low"],
                range_high=entry["range_high"],
                unit=entry["unit"]
            )
            return LabRangeResponse(
                result=details,
                source_version=SOURCE_VERSION,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    raise HTTPException(
        status_code=404,
        detail=f"No reference range found for test '{test}' matching age {age} and sex '{sex}'."
    )
