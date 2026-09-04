#!/usr/bin/env bash
set -e

FHIR_URL=${FHIR_BASE_URL:-"http://localhost:8080/fhir"}
MAX_RETRIES=30
RETRY_INTERVAL=5

echo "Waiting for FHIR server at ${FHIR_URL} to become healthy..."

for i in $(seq 1 $MAX_RETRIES); do
  if curl -s -f "${FHIR_URL}/metadata" > /dev/null; then
    echo "FHIR server is healthy!"
    exit 0
  fi
  echo "Attempt $i/$MAX_RETRIES: FHIR server not ready yet. Waiting ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

echo "Error: FHIR server failed to become healthy within timeout."
exit 1
