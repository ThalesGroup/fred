# CLAUDE.md

Repository-wide instructions for Claude Code.

## Mandatory Read Order

1. [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md)
2. [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)
3. [`docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
4. [`docs/platform/REBAC.md`](./docs/platform/REBAC.md) when access/team behavior is touched
5. [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/design/RUNTIME-EXECUTION-CONTRACT.md) when touching execution contracts, `fred-sdk`, `fred-runtime`, runtime OpenAPI, frontend runtime typing, the CLI, or runtime observability/tracing/KPI/Langfuse metadata
6. [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) when touching control-plane product/session/admin APIs or frontend migration away from `agentic-backend`
7. [`docs/backlog/BACKLOG.md`](./docs/backlog/BACKLOG.md) for migration phase status and next-step sequencing
8. [`docs/WORKPLAN.md`](./docs/WORKPLAN.md) for current sprint assignments and parallel work — always read before starting any task to avoid duplicating in-progress work
9. [`docs/backlog/FRONTEND-BACKLOG.md`](./docs/backlog/FRONTEND-BACKLOG.md) when touching frontend bootstrap, session, or team identity
10. [`docs/backlog/CHAT-UI-BACKLOG.md`](./docs/backlog/CHAT-UI-BACKLOG.md) when touching `ManagedChatPage`, chat UI components, or SSE event rendering

## Non-Negotiable Defaults

- Keep scope minimal. No over-engineering.
- Do not invent a new architecture, endpoint family, or migration direction.
- Do not take product or architecture initiatives when the docs already define the split.
- Use existing conventions and existing Make targets.
- Run `make code-quality` and `make test` in each touched project.
- Keep default tests offline. Any external dependency test must be marked `integration`.
- Prefer stronger typing on existing contracts over new wrappers or ad hoc payloads.
- Never hand-edit generated files such as `frontend/src/slices/runtime/runtimeOpenApi.ts`; regenerate them from source contracts.
- If docs and code diverge, update the docs in the same change.

## Fred Runtime Topology

Canonical source:

- [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)

This defines:

- `fred-runtime` (execution surface, target), Knowledge Flow API, Control Plane API responsibilities.
- `agentic-backend` is being migrated out — do not add execution logic there.
- Knowledge Flow / Agentic / Control Plane Temporal worker responsibilities.

## Active Migration

Fred is mid-migration from `agentic-backend` to `fred-runtime` + `control-plane-backend`.

- New execution code → `fred-runtime` / `fred-sdk`
- New product/session/admin code → `control-plane-backend`
- Migration plan: [`docs/backlog/BACKLOG.md`](./docs/backlog/BACKLOG.md) (Phases 0–6)
- Phase 1 execution contracts frozen: [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/design/RUNTIME-EXECUTION-CONTRACT.md)
- Phase 3a product boundary: [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md)

## Continuation Rules

When continuing the migration:

- treat `docs/design/RUNTIME-EXECUTION-CONTRACT.md` as the execution contract source of truth
- treat `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` as the product/session/admin source of truth for Phase 3a
- treat `docs/backlog/BACKLOG.md` as the sequencing and status source of truth
- prefer editing contract source files over adding compatibility layers
- if a needed type is missing, fix `fred-sdk` or the FastAPI schema first and regenerate instead of adding local mirror DTOs
- do not recreate `agentic-backend` behavior inside `fred-runtime`
- do not add abstractions “for later”; add only what the current phase needs
- if the documentation leaves a migration choice ambiguous, stop at the smallest safe change and update the docs/backlog rather than improvising
- if several options exist, choose the smallest one aligned with the documented architecture
