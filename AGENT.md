# AGENT.md

Quick orientation for AI coding assistants. Read this first, then follow the
links to the relevant contracts.

## What Fred Is

Fred is a production-ready platform for building and operating multi-agent AI
applications. It has three planes:

- **Execution** — `libs/fred-runtime` + `apps/fred-agents` (FastAPI SSE pod)
- **Product / tenancy** — `control-plane-backend` (team, sessions, enrollment)
- **Knowledge** — `knowledge-flow-backend` (document ingestion + vector search)
- **Frontend** — `frontend/` (React, rework design system)

`agentic-backend` is being migrated out. Do not add execution logic there.

## Mandatory Context

Read in this order before making changes:

1. [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md) — build, test, PR rules
2. [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md) — canonical service map
3. [`docs/backlog/BACKLOG.md`](./docs/backlog/BACKLOG.md) — migration phase status (Phases 0–7)
4. [`docs/WORKPLAN.md`](./docs/WORKPLAN.md) — current sprint, who owns what
5. [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/design/RUNTIME-EXECUTION-CONTRACT.md) — when touching fred-runtime, fred-sdk, SSE, CLI, KPI
6. [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) — when touching control-plane APIs or sessions
7. [`docs/backlog/CHAT-UI-BACKLOG.md`](./docs/backlog/CHAT-UI-BACKLOG.md) — when touching ManagedChatPage or chat UI components

## Key Rules

- `agent_instance_id` is the only frontend execution identity — never raw `agent_id`
- `session_id` is the only conversation identifier — never `thread_id`
- Control-plane owns product/tenancy/authorization; runtime owns execution only
- Frontend reads message history from runtime (`messages_url_template`), never from control-plane
- Never hand-edit generated files (`runtimeOpenApi.ts`, `controlPlaneOpenApi.ts`) — regenerate from source
- Run `make code-quality && make test` in every touched project

## Common Make Targets

| Project | Run | Test | Quality |
|---|---|---|---|
| `libs/fred-sdk` | — | `make test` | `make code-quality` |
| `libs/fred-runtime` | `make run` | `make test` | `make code-quality` |
| `control-plane-backend` | `make run` | `make test` | `make code-quality` |
| `knowledge-flow-backend` | `make run` | `make test` | `make code-quality` |
| `frontend` | `make run` | — | `make code-quality` |

## Doc Index

Full documentation index: [`docs/README.md`](./docs/README.md)
