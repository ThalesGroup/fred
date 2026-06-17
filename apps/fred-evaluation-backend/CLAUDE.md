# CLAUDE.md (Fred Evaluation Backend Workspace)

When this folder is opened as the workspace root, apply repository-wide instructions from:

- [`../../CLAUDE.md`](../../CLAUDE.md)
- [`../../docs/swift/platform/DEVELOPER_CONTRACT.md`](../../docs/swift/platform/DEVELOPER_CONTRACT.md)
- [`../../docs/swift/platform/PLATFORM_RUNTIME_MAP.md`](../../docs/swift/platform/PLATFORM_RUNTIME_MAP.md)

---

## What this app is

Dedicated evaluation backend for Fred (`EVAL-01`). Owns evaluation campaigns,
datasets, scoring, results, and optional OTel export.

Does **not** own platform identity, teams, permissions, or runtime catalog —
those belong to the Control Plane.

---

## Architecture

```
campaigns/     — campaign API, models, store, service, schemas
execution/     — Control Plane client, runtime resolver (Phase 3)
scoring/       — ScorerPort, DeepEval adapter (Phase 4)
workers/       — campaign runner, Temporal workflow (Phase 5)
telemetry/     — OTel exporter (Phase 7)
migrations/    — Alembic, version table: alembic_version_evaluation
config/        — YAML config loader, PostgresStoreConfig (SQLite in dev)
```

## Key design decisions

- **Separate app** — not inside Control Plane. Each layer owns its domain.
- **`run_id`** — every campaign creates a `run_id`. Re-running a campaign creates a new run without overwriting previous results.
- **SSE** — `GET /campaigns/{id}/events` streams progress events in real time. Reconnectable via `seq`.
- **ScorerPort** — universal interface between the worker and any scorer (DeepEval today, replaceable tomorrow).
- **`PostgresStoreConfig`** — fred-core handles both SQLite (dev) and PostgreSQL (prod) via the same config model.

---

## Base URL

`/evaluation/v1`

## Port

`8333`

---

## Key commands

```bash
make run          # start API (SQLite, no auth)
make rrun         # start API with hot reload
make run-worker   # start evaluation worker
make test         # run unit tests
make code-quality # ruff + format check
```

## First-time setup

```bash
uv sync
CONFIG_FILE=./config/configuration.yaml uv run alembic upgrade head
make run
```

---

## DB tables

| Table | Description |
|---|---|
| `evaluation_campaign` | Campaign definition and aggregated verdict |
| `evaluation_run` | One execution of a campaign |
| `evaluation_case` | Individual test case with input/output/verdict |
| `evaluation_metric_result` | Per-metric scorer result |
| `evaluation_event` | SSE progress events emitted by the worker |
| `evaluation_export_delivery` | OTel/MLflow/Langfuse export delivery tracking |

---

## TODO (upcoming phases)

- Phase 3 — Control Plane client (runtime resolution)
- Phase 4 — ScorerPort + DeepEval adapter
- Phase 5 — Worker execution (Temporal)
- Phase 6 — Frontend pages
- Phase 7 — OTel export
- Schema rename: `public` → `evaluation` in PostgreSQL
- OpenAPI generation + frontend generated client
