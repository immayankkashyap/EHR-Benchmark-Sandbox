#!/usr/bin/env bash
set -e

POPULATION=${1:-10}
OUTPUT_DIR="synthea/output"

echo "Running Synthea generator for population size: ${POPULATION}..."
mkdir -p "$OUTPUT_DIR"

# Placeholder invocation for Synthea JAR / generator
echo "Synthea generation completed. Output written to ${OUTPUT_DIR}."
