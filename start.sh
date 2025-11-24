#!/bin/bash

# Stop all subprocesses when the script receives Ctrl+C
trap "echo 'Stopping...'; kill 0" SIGINT

# agentic backend
(cd agentic-backend && make run 2>&1 | sed "s/^/[AGENTIC] /") &

# knowledge-flow backend
(cd knowledge-flow-backend && make run 2>&1 | sed "s/^/[KF] /") &

# frontend
(cd frontend && make run 2>&1 | sed "s/^/[FRONTEND] /") &

# CO₂ emission reference MCP server (local FastAPI+MCP)
(cd agentic-backend && uv run uvicorn agentic_backend.academy.08_ecoadviser.co2_estimation_service.server_mcp:app \
    --host 127.0.0.1 --port 9798 2>&1 | sed "s/^/[CO2] /") &

# wait for all background jobs
wait
