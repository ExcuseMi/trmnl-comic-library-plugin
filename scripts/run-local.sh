#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Installing Python dependencies ==="
pip install -q requests pyyaml python-dotenv

echo "=== Building feed validator Docker image ==="
cp plugin/transform.js scripts/node-validator/transform.js
docker build -t trmnl-feed-validator scripts/node-validator/

echo "=== Generating updated comic options ==="
python scripts/generate-options.py

echo "=== Done ==="
