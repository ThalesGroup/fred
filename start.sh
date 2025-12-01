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

# Also load agentic-backend/config/.env if present (agent-specific secrets)
ADDITIONAL_ENV="$ROOT_DIR/agentic-backend/config/.env"
if [[ -f "$ADDITIONAL_ENV" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ADDITIONAL_ENV"
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
echo "→ GRANDLYON_WFS_URL=${GRANDLYON_WFS_URL:-https://data.grandlyon.com/geoserver/metropole-de-lyon/ows}"
echo "→ GRANDLYON_WFS_TYPENAME=${GRANDLYON_WFS_TYPENAME:-metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic}"
if [[ -z "${GRANDLYON_WFS_API_KEY:-}" && ( -z "${GRANDLYON_WFS_USERNAME:-}" || -z "${GRANDLYON_WFS_PASSWORD:-}" ) ]]; then
  echo "⚠️  No GrandLyon WFS credentials found (GRANDLYON_WFS_API_KEY or USERNAME/PASSWORD). Traffic MCP may be rejected."
fi

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

# Traffic reference MCP server
(cd agentic-backend && uv run uvicorn agentic_backend.academy.08_ecoadviser.traffic_service.server_mcp:app \
    --host 127.0.0.1 --port 9799 2>&1 | prefix_logs "TRAFFIC") &

# TCL real-time MCP server
(cd agentic-backend && uv run uvicorn agentic_backend.academy.08_ecoadviser.tcl_service.server_mcp:app \
    --host 127.0.0.1 --port 9800 2>&1 | prefix_logs "TCL") &

# wait for all background jobs
wait
