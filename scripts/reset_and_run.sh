#!/usr/bin/env bash
set -e

echo "Resetting environment and restarting containers..."
docker-compose down -v
docker-compose up -d

echo "Environment reset complete."
