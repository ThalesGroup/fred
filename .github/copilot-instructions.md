# Fred AI Coding Instructions

## Big Picture (Read First)
- Three services: `agentic-backend/` (FastAPI + LangGraph agents), `knowledge-flow-backend/` (FastAPI ingestion + vector search + MCP endpoints), `frontend/` (React + Vite UI).
- Agent behavior lives in `agentic-backend/config/configuration.yaml` (agents, MCP servers, feature flags, model providers).
- Ingestion + storage pipelines live in `knowledge-flow-backend/config/configuration.yaml` (input/output processors, storage backends, embeddings).
- The frontend consumes both APIs via generated RTK Query hooks; regenerate after OpenAPI changes.

## Critical Workflows
- Start services via Makefiles: `make run` in `agentic-backend/` (port 8000), `knowledge-flow-backend/` (port 8111), and `frontend/` (port 5173).
- Temporal workers are separate: `make run-worker` in `agentic-backend/` and `knowledge-flow-backend/` when needed.
- Secrets go in each backend’s `config/.env`; non-secret config stays in `configuration.yaml`.
- Dev Container setup is supported (see root `README.md`).

## Frontend Conventions
- Use MUI components and the app theme from `theme.tsx`.
- All UI copy must use `react-i18next` (`t` from `useTranslation`) and update `src/locales/{lang}/translation.json`.
- Use `Link` from `react-router-dom` for navigation; ensure `to` is a valid route.
- Regenerate API clients when backend schemas change: `make update-agentic-api` or `make update-knowledge-flow-api` (run from `frontend/`).
- Format with `prettier` (via `make format`).

## Python Backend Conventions
- Use `uv` for dependency management.
- Each backend has its own `.venv`; run scripts with `.venv/bin/python` to ensure correct deps.
- Use type hints everywhere and prefer Python 3.10+ unions (`str | None`).
- Format with `ruff` (e.g., `make format` in `knowledge-flow-backend/`).
