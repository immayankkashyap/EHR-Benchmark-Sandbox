"""
Phase: Auxiliary Tools - Drug Interaction Checker
Purpose: Service entrypoint providing API endpoints to query drug-drug interactions and contraindications.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

SOURCE_VERSION = "v2026-09-04"

# Pydantic Schemas
class InteractionDetails(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    description: str

class InteractionResponse(BaseModel):
    result: InteractionDetails
    source_version: str
    timestamp: str

# Data Store
interactions_db: List[Dict[str, str]] = []

def load_data():
    """Load interactions data into memory."""
    global interactions_db
    data_path = Path(__file__).parent / "data" / f"interactions_{SOURCE_VERSION}.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            interactions_db = json.load(f)

# Lifespan context manager for startup/shutdown
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    yield
    # Shutdown logic if any

app = FastAPI(title="Drug Interaction Checker", version="1.0.0", lifespan=lifespan)

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "drug-interaction-checker"}

@app.get("/check-interaction", response_model=InteractionResponse)
def check_interaction(
    drug_a: str = Query(..., description="First drug name"),
    drug_b: str = Query(..., description="Second drug name")
):
    """Check interactions between two drugs."""
    da = drug_a.lower().strip()
    db = drug_b.lower().strip()
    
    for interaction in interactions_db:
        ia = interaction["drug_a"].lower()
        ib = interaction["drug_b"].lower()
        
        # Order independent match
        if (ia == da and ib == db) or (ia == db and ib == da):
            return InteractionResponse(
                result=InteractionDetails(**interaction),
                source_version=SOURCE_VERSION,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
    # If no interaction found, return a default "no known interaction" message as 404
    raise HTTPException(
        status_code=404,
        detail=f"No known interaction found between {drug_a} and {drug_b}."
    )
