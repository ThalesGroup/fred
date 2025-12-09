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
echo "→ GEO_NOMINATIM_URL=${ECO_GEO_NOMINATIM_URL:-https://nominatim.openstreetmap.org/search}"
echo "→ GEO_OSRM_URL=${ECO_GEO_OSRM_URL:-https://router.project-osrm.org}"
ECO_AGENT_DIR="$ROOT_DIR/agentic-backend/agentic_backend/academy/08_ecoadviser"
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

# EcoAdvisor MCP services bundle
(cd "$ECO_AGENT_DIR" && make run 2>&1 | prefix_logs "ECO") &

# wait for all background jobs
wait
