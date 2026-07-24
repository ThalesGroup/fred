---
name: live-observability-session
description: Start Fred's backends and watch their logs/metrics/audit trail live while the developer drives the frontend/chat by hand. Use for manual observability or KPI test campaigns, or to diagnose a "does X actually log/emit/audit correctly" question against the three-stream model in OBSERVABILITY-AND-AUDIT.md.
user-invocable: true
argument-hint: [optional: which backends — default 3 core APIs + 2 Temporal workers; add fred-evaluation-backend (+worker) when the session involves agent evaluation]
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

**Agent evaluation adds a fourth app, in a separate sibling repo** —
`~/Fred/fred-agent-evaluator/apps/fred-evaluation-backend` (not under `~/Fred/fred`). Include it
whenever the session involves running or checking an agent evaluation/scoring campaign:

| App | Command | Port | Has a Temporal worker? |
|---|---|---|---|
| `fred-agent-evaluator/apps/fred-evaluation-backend` | `make run` | 8336 | yes — `make run-worker-prod` (not plain `run-worker`: this target exports `CONFIG_FILE=configuration_prod.yaml` explicitly and enables M2M against Keycloak, matching how the other three backends run in this stack) |

Its `config/.env` already pins `CONFIG_FILE` to `configuration_prod.yaml` by default (check it
like the others, don't assume). **This backend's prod config disables both `prometheus` and
`opensearch` in its logging/metrics block** (`configuration_prod.yaml` → `logging.prometheus.enabled:
false`, `logging.opensearch.enabled: false`) — its `/metrics` route 404s and it does not feed the
shared `app-logs-index`. Don't report either as broken; it's the app's own config, not a bug. Its
only live signal in this stack is its own stdout (Monitor it the same way as the other three) plus
whatever it writes to Postgres/Temporal directly.

That's up to 7 background processes when evaluation is in scope (4 APIs + 3 workers), or 5 when
it isn't (3 APIs + 2 workers). Launch whichever set is in scope in parallel — independent Bash
calls in one message — not sequentially. If the developer only cares about one slice (e.g. "just
check ingestion KPIs"), ask which subset before launching all of them; don't pay the startup cost
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
   endpoint directly. **The metrics port is not always the API port — check each app's own
   `configuration_prod.yaml` (`logging.prometheus.port`), never assume it equals the API port:**

   | App | API port | Metrics port | Source |
   |---|---|---|---|
   | control-plane-backend | 8222 | **9222** | `configuration_prod.yaml` → `logging.prometheus.port` |
   | knowledge-flow-backend | 8111 | **9111** | same |
   | fred-agents | 8000 | none | no `logging`/`prometheus` block at all in `configuration_prod.yaml` — this app does not expose metrics in this stack, not merely "disabled" |
   | fred-evaluation-backend | 8336 | none | `logging.prometheus.enabled: false` (see above) |

   e.g. `curl localhost:9222/metrics` (control-plane), `curl localhost:9111/metrics`
   (knowledge-flow) — grep the raw Prometheus-exposition text output for the metric name you care
   about. Don't curl `fred-agents` or `fred-evaluation-backend` for metrics — neither exposes a
   `/metrics` route in this stack, for two different reasons (see table). If the developer's
   session *does* have a real Prometheus reachable (a different, non-default setup), `curl
   localhost:9090/api/v1/query?query=...` works the same way — don't assume either way, check the
   port first. Every label actually reaching the KPI store is filtered through
   `PROMETHEUS_ALLOWED_LABELS` in `libs/fred-core/fred_core/kpi/prometheus_kpi_store.py` — if a
   finding claims a label is missing or present, check that allow-list before concluding anything;
   it's an enforced allow-list, not a convention callers might violate.

Metric name note: dots are sanitized to underscores on the wire (`llm.call_latency_ms` in code →
`llm_call_latency_ms` both in the raw `/metrics` exposition text and in a PromQL query, if one is
available).

## Watching KPI hygiene and completeness, not just a one-shot curl

A single `curl .../metrics` only tells you the KPI state at the instant you ran it — it won't tell
you whether an action the developer just took in the UI actually produced the expected metric, or
whether an unexpected label slipped past `PROMETHEUS_ALLOWED_LABELS`. Treat metrics as a third live
stream to watch continuously via **Monitor**, the same way stdout is — not as an on-demand lookup
done once at session start and never revisited.

Diff-poll each exposing app's metrics endpoint (correct port — see table above) and emit only what
changed, the same "poll external state, emit one line per new thing" pattern Monitor uses for
polling a GitHub PR for new comments:

    prev=""
    while true; do
      cur=$(curl -s --max-time 3 http://localhost:9222/metrics | grep -v '^#')
      diff <(echo "$prev") <(echo "$cur") | grep -E '^[<>]' || true
      prev="$cur"
      sleep 5
    done

Run one such loop per app that actually exposes `/metrics` (control-plane, knowledge-flow in this
stack — not fred-agents or fred-evaluation-backend). Use it to confirm, in near-real time as the
developer drives the UI: a new metric family appears the first time an action fires it
(completeness — did this action actually emit a KPI at all), a counter/histogram that should
increment on a given action actually does (correctness), and no label value shows up that isn't in
`PROMETHEUS_ALLOWED_LABELS` (hygiene). Report a finding the same way as any other — reproduction,
extract (the diff line), channel (`KPIs`), classification — don't just note "metrics look fine"
without a concrete diff to back it.

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

## Reporting discipline — silence is the default

A live session generates a Monitor notification for every stdout line and every KPI poll tick —
most of it is expected noise (routine audit grants, known warnings already tracked in an issue,
routine request/response pairs). Do not send a chat message for each one. Acknowledging every
notification with something like "rien de nouveau" or "RAS" defeats the purpose of a live session
just as much as missing a real finding does — it buries the signal the developer actually needs
under a wall of empty turns.

Default to **no reply at all** for a notification that matches something already known:
- A pattern already reported and tracked in an issue (e.g. an audit line already logged as a
  known-noisy call site) — stays silent on every recurrence, not just after the first mention.
- A KPI diff that's just the expected counter/histogram increment for an action the developer is
  visibly repeating (e.g. polling, page navigation).
- Routine startup/shutdown lines (SQL engine creation, MCP route registration, health checks).

Only produce a message when at least one of these is true:
- **A genuinely new signal**: an error, traceback, or warning that has not appeared before in
  this session, or a KPI diff on a route/label combination not yet seen.
- **A qualitative change** in an already-known pattern (e.g. a known-permanent failure starts
  succeeding, a retry count crosses a threshold that changes its classification, a warning that
  was cosmetic starts appearing alongside an actual error).
- **The developer asks a direct question** or reports something to diagnose.
- **A finding is ready to report** per the four-part format above — reproduction, extract,
  channel, classification — not a partial or "maybe" observation.

If the harness nudges for "no visible output" after several silent turns, that's a framework
concern, not a signal to start narrating routine noise again — keep tool-only or fully silent
turns whenever nothing new happened, and say so explicitly to the developer once (not every
time) if asked to explain why a turn produced no text.

## Ending the session

Stop whichever background processes this session started (5 without evaluation in scope, 7 with
`fred-evaluation-backend` included) when the developer is done — or when they start a `make clean`
/ infra wipe cycle (those invalidate the running `.venv`s and containers respectively) either in
`~/Fred/fred` or, separately, in `~/Fred/fred-agent-evaluator`. Don't leave them running silently
across an unrelated task.
