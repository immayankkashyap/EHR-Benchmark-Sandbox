#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# The Python verifier checks successful execution separately from blocked sockets.
exec .venv/bin/python scripts/verify_isolation.py
