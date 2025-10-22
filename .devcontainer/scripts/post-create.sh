#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)/.."
cd "${ROOT_DIR}"

if [[ ! -d "fred-core/.venv" ]]; then
  (cd "fred-core" && make dev)
fi

if [[ ! -d "agentic-backend/.venv" ]]; then
  (cd "agentic-backend" && make dev)
fi

if [[ ! -d "knowledge-flow-backend/.venv" ]]; then
  (cd "knowledge-flow-backend" && make dev)
fi

if [[ ! -d "frontend/node_modules" ]]; then
  (cd "frontend" && make node_modules)
fi

echo "✅ Fred dev container bootstrap complete."
