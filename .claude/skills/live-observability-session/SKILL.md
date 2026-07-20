---
name: live-observability-session
description: Start Fred's backends and watch their logs/metrics/audit trail live while the developer drives the frontend/chat by hand. Use for manual observability or KPI test campaigns, or to diagnose a "does X actually log/emit/audit correctly" question against the three-stream model in OBSERVABILITY-AND-AUDIT.md.
user-invocable: true
argument-hint: [optional: which backends — default all 3 APIs + both Temporal workers]
---

# Live Observability Session

A **collaborative** working mode, not an automated test run: the developer drives the UI (chat,
admin console, whatever's under test) by hand; you start the backends, tail their stdout, poll
OpenSearch/KPIs, and report what you see. You never click through the frontend or hit
business endpoints yourself — see "The protocol" below. This mirrors how a real observability
review is done: the developer reproduces a scenario, you read the resulting signal across all
three streams and say what's there, what's missing, and what's wrong.

**Scope: this skill targets the `fred-deployment-factory` local dev stack on the `swift` branch**
(Postgres/Keycloak/OpenSearch/Temporal via `docker compose` + backends run natively with `make
run`). It does not apply as-is to a k3d/Kubernetes deployment or other branches/deployment
targets — port numbers, the absence of a standalone Prometheus, and the `make run`-based backend
startup are all specific to this stack. If the developer is on a different deployment target, ask
before assuming any of the below still holds.

## Preconditions — infra is the developer's job, not yours

Postgres, Keycloak, OpenSearch, Temporal (and optionally Grafana/Langfuse) run via docker compose
files in `~/Fred/fred-deployment-factory/docker/docker-compose-<service>.yml`, orchestrated by
that repo's own `Makefile` (`DOCKER_COMPOSE_BASE`, `make docker-up`). **Do not start, stop, or
wipe this infra yourself** — confirm with the developer that it's up (they may be mid-"wipe and
up" cycle) before starting any backend. Known ports, for when you need to query a stream directly:

| Service | Port | Notes |
|---|---|---|
| Keycloak | 8080 | |
| OpenSearch | 9200 | Dashboards UI on 5601 |
| Temporal | 7233 (gRPC) | Web UI on 8233 |
| Grafana | 3002 | if the developer has it up — not part of `make docker-up` by default |

**No Prometheus in this stack.** `make docker-up` does not bring up a standalone Prometheus or
Grafana — there is no central `localhost:9090` to query. KPIs must be read by curling each
backend's own `/metrics` endpoint directly once it's running (see "The three streams" below).
Don't assume a central Prometheus exists just because other Fred docs/skills mention one — verify
per session.

If any of the services in the table above isn't reachable, say so and ask the developer to bring
it up — don't guess or skip the check.

## Starting the backends

**Check the `.env` first.** Each backend's `config/.env` must point `CONFIG_FILE` at
`configuration_prod.yaml` (not the default `configuration.yaml`) for `make run` to target this
shared docker-compose infra correctly. Confirm with the developer rather than assuming — if
`.env` points elsewhere, backends may start against the wrong config silently.

Run each from its own app directory at the monorepo root (`~/Fred/fred`), each in the background
(`run_in_background: true`) so you can keep working while they serve:

| App | Command | Port | Has a Temporal worker? |
|---|---|---|---|
| `apps/control-plane-backend` | `make run` | 8222 | yes — `make run-worker` |
| `apps/knowledge-flow-backend` | `make run` | 8111 | yes — `make run-worker` |
| `apps/fred-agents` | `make run` | 8000 | no |

That's up to 5 background processes (3 APIs + 2 workers). Launch them in parallel — independent
Bash calls in one message — not sequentially. If the developer only cares about one slice (e.g.
"just check ingestion KPIs"), ask which subset before launching all 5; don't pay the startup cost
of backends that aren't part of this session's question.

`make run` installs deps first if needed (`run: dev run-local`) — the first launch after a
`make clean` will be slower; don't mistake that startup delay for a hang.

## Watching, don't polling

Use the **Monitor** tool against each backend's background shell to stream stdout live — every
line becomes a notification — rather than periodically re-reading a log file or sleep-looping.
This is the same distinction the harness itself calls out: polling wastes turns and misses the
moment; Monitor surfaces each line as it's written, which is what lets you correlate "developer
just clicked X" with the log line it produced in near real time.

## The three streams — what "checking observability" actually means

Ground every finding in `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` (read it once per
session if it's been a while — it's the target spec, not always the current diff). In short:

1. **stdout** — every backend's console handler; also where the **audit logger**
   (`fred.security.audit`) writes exclusively, as structured JSON, `propagate=False`. Audit
   records must appear here and **only** here — if you see one land in OpenSearch's generic
   log index, that's a bug (`StoreEmitHandler` is supposed to hard-drop `AUDIT_LOGGER_NAME`
   records).
2. **OpenSearch** (`curl localhost:9200/app-logs-index/_search`, or Dashboards on 5601) — the
   generic durable app-log store, fed by the same root logger as stdout via `StoreEmitHandler`.
   Fine for anything except audit content and raw prompt/response/tool-argument text (never
   supposed to appear in either stream — check for it if you're chasing a content-leak report).
3. **KPIs / metrics** — operational KPIs only, never prompt/response content. This stack has no
   standalone Prometheus (see Preconditions), so read them by curling each backend's own metrics
   endpoint directly, e.g. `curl localhost:8222/metrics` (control-plane), `localhost:8111/metrics`
   (knowledge-flow), `localhost:8000/metrics` (fred-agents) — grep the raw Prometheus-exposition
   text output for the metric name you care about. If the developer's session *does* have a real
   Prometheus reachable (a different, non-default setup), `curl localhost:9090/api/v1/query?query=...`
   works the same way — don't assume either way, check the port first. Every label actually
   reaching the KPI store is filtered through `PROMETHEUS_ALLOWED_LABELS` in
   `libs/fred-core/fred_core/kpi/prometheus_kpi_store.py` — if a finding claims a label is
   missing or present, check that allow-list before concluding anything; it's an enforced
   allow-list, not a convention callers might violate.

Metric name note: dots are sanitized to underscores on the wire (`llm.call_latency_ms` in code →
`llm_call_latency_ms` both in the raw `/metrics` exposition text and in a PromQL query, if one is
available).

## The protocol

- The developer drives the frontend/chat/admin UI. You do not open a browser, curl a business
  endpoint, or run an automated end-to-end test against the live stack yourself — that's the
  standing rule for this kind of session (live testing is collaborative, not something you do
  autonomously). If you think a specific action would help diagnose something, propose it and
  let the developer perform it, or ask before running it yourself.
- When the developer reports something ("it didn't search the RAG", "the latency looks wrong"),
  diagnose from the logs **first** — don't guess at a root cause before reading what actually
  happened. Only form a hypothesis about code after the log evidence points somewhere.
- Report every finding with all four of: **reproduction** (what the developer just did),
  **extract** (the actual log line(s)/metric/query result — quote it, don't paraphrase),
  **channel** (stdout / OpenSearch / KPIs / audit), and **classification** (bug, config
  gap, expected-but-underdocumented behavior, or false alarm). A finding missing any of these
  four isn't ready to report yet.
- If a fix is warranted, follow this repo's normal rule from `CLAUDE.md`: fix the root cause,
  never a patch over the symptom, and use the correct generic hook/abstraction rather than a
  point patch — if the fix is non-trivial and you're deep into a large context already, it's
  fine to hand it to a fresh background agent with a precise, self-contained prompt rather than
  cram it into this session.

## Ending the session

Stop the 5 background processes when the developer is done (or when they start a `make clean` /
infra wipe cycle — those invalidate the running `.venv`s and containers respectively). Don't leave
them running silently across an unrelated task.
