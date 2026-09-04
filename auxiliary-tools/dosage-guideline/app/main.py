"""
Phase: Auxiliary Tools - Dosage Guideline
Purpose: Service entrypoint providing API endpoints for querying recommended medication dosing guidelines.
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
class DosageGuidelineDetails(BaseModel):
    drug: str
    indication: str
    weight_min_kg: float
    weight_max_kg: float
    dosage: str
    frequency: str
    max_daily_dose: str

class DosageGuidelineResponse(BaseModel):
    result: DosageGuidelineDetails
    source_version: str
    timestamp: str

# Data Store
dosage_db: List[Dict[str, Any]] = []

def load_data():
    """Load dosage guideline data into memory."""
    global dosage_db
    data_path = Path(__file__).parent / "data" / f"dosage_guidelines_{SOURCE_VERSION}.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            dosage_db = json.load(f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    yield

app = FastAPI(title="Dosage Guideline Service", version="1.0.0", lifespan=lifespan)

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "dosage-guideline"}

@app.get("/dosage", response_model=DosageGuidelineResponse)
def get_dosage_guideline(
    drug: str = Query(..., description="Name of the medication"),
    indication: Optional[str] = Query(None, description="Clinical indication for the drug"),
    weight_kg: Optional[float] = Query(None, description="Patient weight in kg")
):
    """Retrieve dosage guideline for a medication based on indication and weight."""
    drug_query = drug.lower().strip()
    ind_query = indication.lower().strip() if indication else None
    
    # Defaults if not provided (to match "all" cases if we had them)
    weight = weight_kg if weight_kg is not None else 70.0  # Assumed adult weight if not given

    for entry in dosage_db:
        if entry["drug"].lower() == drug_query:
            # Match indication if provided, otherwise assume first match
            if ind_query and entry.get("indication", "").lower() != ind_query:
                continue
            
            # Match weight range
            if entry["weight_min_kg"] <= weight <= entry["weight_max_kg"]:
                details = DosageGuidelineDetails(
                    drug=entry["drug"],
                    indication=entry["indication"],
                    weight_min_kg=entry["weight_min_kg"],
                    weight_max_kg=entry["weight_max_kg"],
                    dosage=entry["dosage"],
                    frequency=entry["frequency"],
                    max_daily_dose=entry["max_daily_dose"]
                )
                return DosageGuidelineResponse(
                    result=details,
                    source_version=SOURCE_VERSION,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

    raise HTTPException(
        status_code=404,
        detail=f"No dosage guideline found for drug '{drug}' matching indication '{indication}' and weight {weight}kg."
    )
