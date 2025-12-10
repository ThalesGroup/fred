#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Stop all subprocesses when the script receives Ctrl+C
trap "echo 'Stopping...'; kill 0" SIGINT

prefix_logs() {
  local label="$1"
  sed "s/^/[$label] /"
}

ECO_AGENT_DIR="$REPO_ROOT/agentic-backend/agentic_backend/academy/08_ecoadviser"

# agentic backend
(cd "$REPO_ROOT/agentic-backend" && make run 2>&1 | prefix_logs "AGENTIC") &

# knowledge-flow backend
(cd "$REPO_ROOT/knowledge-flow-backend" && make run 2>&1 | prefix_logs "KF") &

# frontend
(cd "$REPO_ROOT/frontend" && make run 2>&1 | prefix_logs "FRONTEND") &

# EcoAdvisor MCP services bundle
(cd "$ECO_AGENT_DIR" && make run 2>&1 | prefix_logs "ECO") &

# wait for all background jobs
wait
