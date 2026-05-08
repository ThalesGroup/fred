# AGENTS.md

All coding assistants working in this repository must follow:

- [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/swift/platform/DEVELOPER_CONTRACT.md)
- [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/swift/platform/PLATFORM_RUNTIME_MAP.md)
- [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md) when touching `fred-sdk`, `fred-runtime`, runtime OpenAPI, frontend runtime typing, the CLI, or runtime observability/tracing/KPI/Langfuse metadata
- [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) when touching control-plane product/session/admin APIs or frontend migration away from `agentic-backend`
- [`docs/backlog/BACKLOG.md`](./docs/swift/backlog/BACKLOG.md) for migration phase status and next-step sequencing
- [`docs/WORKPLAN.md`](./docs/swift/WORKPLAN.md) for current sprint assignments — read before starting any task to avoid duplicating in-progress work
- [`docs/backlog/FRONTEND-BACKLOG.md`](./docs/swift/backlog/FRONTEND-BACKLOG.md) when touching frontend bootstrap, session, or team identity
- [`docs/backlog/CHAT-UI-BACKLOG.md`](./docs/swift/backlog/CHAT-UI-BACKLOG.md) when touching `ManagedChatPage`, chat UI components, or SSE event rendering

Mandatory defaults:

- Keep changes minimal and avoid over-engineering.
- Do not invent new architecture, new convergence layers, or undocumented product behavior.
- Do not take initiative on architecture when the docs already define the split; follow the documented split.
- Run `make code-quality` and `make test` in every touched project.
- Keep default tests offline (no external service dependency).
- Mark external-service tests as `integration`.
- For all default validation, assume zero third-party services are running (no MinIO, OpenSearch, Postgres, Keycloak, OpenFGA, Temporal, etc.).
- Prefer strengthening existing typed contracts over adding ad hoc `dict[str, Any]` payloads.
- When extending `fred-sdk` or `fred-runtime`, first look for transitional bridges or duplicate request/state shapes and prefer collapsing them over threading new fields through every layer.
- Do not add feature-specific side channels for `TeamAgent` or other one-off use cases when the real seam belongs in a shared runtime/SDK contract.
- Do not introduce a second transport or execution request shape for a special case if the existing typed runtime contract can be extended instead.
- Never hand-edit generated files such as `frontend/src/slices/runtime/runtimeOpenApi.ts`; edit the source contract and regenerate.
- If a needed type is missing, first strengthen the source contract or FastAPI schema and regenerate; do not add shadow DTOs in the frontend.
- If the docs do not answer a migration decision, stop at the smallest safe change and update the docs/backlog instead of inventing a path.
- Every new/modified function must document:
  - why it exists
  - how to use it
  - and include a short usage example for shared helpers/public utility functions.
- Keep functions intentional: business function or necessary shared helper that removes duplication.
- For each new feature/improvement, prefer codebase shrink/reuse/refactor over net code growth.
- When migration docs and implementation diverge, update the relevant docs in the same change.
