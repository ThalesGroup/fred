# AGENT.md

Guidance for AI coding assistants working in the Fred repository. Follow these notes to get context quickly and stay aligned with existing workflows.

## Project Snapshot
- Fred is a production-ready, multi-agent AI platform.
- Three top-level services: `agentic_backend/` (LangGraph orchestration), `knowledge_flow_backend/` (document ingestion + vector search), `frontend/` (React UI).
- Python services target Python 3.12.8 with `pyenv` + `python3-venv`; frontend targets Node.js 22.13.0 via `nvm`.

## Getting Started
1. Ensure prerequisites: Python 3.12.8, Node 22.13.0, Make, optional Temporal for ingestion workers.
2. Copy `OPENAI_API_KEY=...` into both backends under `config/.env`.
3. Launch services (separate terminals):
   ```bash
   cd agentic_backend && make run      # FastAPI on :8000
   cd knowledge_flow_backend && make run  # FastAPI on :8111
   cd frontend && make run             # Vite on :5173
   ```

## Common Commands
- **agentic_backend**: `make run`, `make test`, `make test-one TEST=...`, `make clean`.
- **knowledge_flow_backend**: `make run`, `make run-worker`, `make test`, `make lint`, `make lint-fix`, `make format`, `make sast`, `make code-quality`.
- **frontend**: `make run`, `make format`, `make update-knowledge-flow-api`.

## Repository Orientation
- `agentic_backend/` – LangGraph agents, configuration at `config/configuration.yaml`.
- `knowledge_flow_backend/` – Document processors, storage adapters, Temporal workflows, configuration at `config/configuration.yaml`.
- `frontend/` – React 18 + TypeScript app using Vite, Material UI, Redux Toolkit, and RTK Query.
- `docs/`, `deploy/`, `developer_tools/`, `fred-core/`, `scripts/` – supporting assets, tooling, deployment helpers.

## Development Tips
- Respect feature flags and MCP integrations defined in backend configuration files.
- For document processing, align new processors with configuration mappings and update upload validation on the frontend when new file types are added.
- Frontend API clients are generated; run `make update-knowledge-flow-api` after backend OpenAPI changes.
- Use `useToast` for notifications and react-i18next for copy (`frontend/src/locales/...`).
- Prefer repository `Makefile` targets over bespoke commands to stay consistent with existing automation.

## Testing & Quality
- Backends use pytest; add coverage for new logic and ensure async components are exercised.
- `knowledge_flow_backend` runs ruff for lint/format and bandit for SAST; keep these clean.
- Frontend relies on TypeScript checks and formatting via Prettier (through `make format`).

## Security & Ops Notes
- Never commit secrets; rely on `.env` files and documented configuration.
- Production deployments should swap filesystem storage for OpenSearch/MinIO/DuckDB as configured.
- Enable debug logging in `configuration.yaml` when diagnosing workflow/agent issues.

Stay consistent with existing patterns, keep changes minimal and well-tested, and call out cross-service impacts in PR descriptions.
