#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "====================================================="
echo " Resetting Healthcare EHR Sandbox State"
echo "====================================================="

# Step 1: Destroy existing container stack and volumes
echo -e "${YELLOW}[1/4] Tearing down containers and removing persistent volumes...${NC}"
docker compose down -v

# Step 2: Rebuild and start container stack
echo -e "${YELLOW}[2/4] Rebuilding and launching sandbox container services...${NC}"
docker compose up --build -d

# Step 3: Poll HAPI FHIR metadata endpoint until 200 OK
echo -e "${YELLOW}[3/4] Waiting for HAPI FHIR JPA server to become healthy...${NC}"
FHIR_URL="http://localhost:8080/fhir/metadata"
MAX_ATTEMPTS=30
ATTEMPT=0

until [ $ATTEMPT -ge $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FHIR_URL" || echo "000")
    
    if [ "$HTTP_STATUS" -eq 200 ]; then
        echo -e "${GREEN}HAPI FHIR server is ready and responding with HTTP 200 OK!${NC}"
        break
    fi
    
    echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS: FHIR server not ready yet (HTTP $HTTP_STATUS). Retrying in 5 seconds..."
    sleep 5
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo "Error: HAPI FHIR server failed to start within the timeout period."
    exit 1
fi

# Step 4: Ingest baseline clinical case
echo -e "${YELLOW}[4/4] Ingesting baseline clinical case (example_case_001.json)...${NC}"
python3 case-ingestion/ingest_case.py case-ingestion/mock_cases/example_case_001.json

echo "====================================================="
echo -e "${GREEN}Environment reset & initial state loading complete!${NC}"
echo "====================================================="
