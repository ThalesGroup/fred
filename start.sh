#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Load optional local environment overrides
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
fi

CO2_DATA_DEFAULT="$ROOT_DIR/agentic-backend/agentic_backend/academy/08_ecoadviser/reference_api/co2_reference_dataset.json"
export CO2_REFERENCE_DATA="${CO2_REFERENCE_DATA:-$CO2_DATA_DEFAULT}"
export ADEME_BASECARBONE_URL="${ADEME_BASECARBONE_URL:-https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner}"
export ADEME_BASECARBONE_ENABLED="${ADEME_BASECARBONE_ENABLED:-true}"

echo "Starting stack from $ROOT_DIR"
echo "→ CO2_REFERENCE_DATA=$CO2_REFERENCE_DATA"
echo "→ ADEME_BASECARBONE_URL=$ADEME_BASECARBONE_URL"
echo "→ ADEME_BASECARBONE_ENABLED=$ADEME_BASECARBONE_ENABLED"

# Stop all subprocesses when the script receives Ctrl+C
trap "echo 'Stopping...'; kill 0" SIGINT

prefix_logs() {
  local label="$1"
  sed "s/^/[$label] /"
}

# agentic backend
(cd agentic-backend && make run 2>&1 | prefix_logs "AGENTIC") &

# knowledge-flow backend
(cd knowledge-flow-backend && make run 2>&1 | prefix_logs "KF") &

# frontend
(cd frontend && make run 2>&1 | prefix_logs "FRONTEND") &

# CO₂ emission reference MCP server (local FastAPI+MCP)
(cd agentic-backend && uv run uvicorn agentic_backend.academy.08_ecoadviser.co2_estimation_service.server_mcp:app \
    --host 127.0.0.1 --port 9798 2>&1 | prefix_logs "CO2") &

# wait for all background jobs
wait
