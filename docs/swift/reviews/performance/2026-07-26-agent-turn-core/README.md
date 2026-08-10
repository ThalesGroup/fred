# Agent turn core — performance and scalability review

Review date: 2026-07-26

Branch:
`2110-observ-02-v3-role-based-dashboards-greencarbon-metrics-models-as-capability-persisted-task-ack`

Reviewed commit: `70437e09`

Scope: one managed question/answer turn, from `POST /agents/execute/stream`
through authorization, runtime activation, LLM/tool execution, SSE delivery,
checkpoint/history persistence, and observability.

This directory is durable review evidence, not a parallel backlog. GitHub
Issues remains the source of truth for priority, ownership, implementation, and
closure. No dedicated issue existed for these findings when the review was
written. Select or create one before implementing each fix and add its URL to
the corresponding dossier.

For the observation → supervision → implementation → revalidation workflow,
including copy/paste prompts for each role, use the
[working protocol](./WORKING-PROTOCOL.md).

The current design authority is
[`RUNTIME-EXECUTION-CONTRACT.md`](../../../design/RUNTIME-EXECUTION-CONTRACT.md).
RFC links in that document preserve historical rationale; they are not the
current operational contract.

## Executive verdict

The base execution architecture has sound foundations:

- the browser streams directly from the runtime pod; the control plane does not
  proxy the SSE response;
- ReAct/Deep LLM calls are asynchronous and use a process-wide HTTP pool with
  explicit connect/read/write/pool timeouts;
- Knowledge Flow clients also share an async HTTP transport;
- ReAct/Deep tool calls use one middleware chokepoint for latency, audit, and
  per-call authorization;
- Graph fan-out groups use `asyncio.gather`;
- history rows are batch-written, and KPI/log stores are protected by the
  resilient sink.

The system is not yet demonstrably safe at the target of 200 concurrent turns.
The dominant risks happen before the first LLM token or multiply with every
tool call. Four P1 gaps are statically confirmed: control-plane authorization
fan-out, Graph runtime observability/authorization divergence, ineffective turn
resource policies, and synchronous Keycloak refresh in async paths. MCP cold
start and pod admission/SQL capacity require representative load evidence.

## Hot-path map

| Stage | Current work for one managed turn | Concurrency/scaling property | Visibility | Verdict |
|---|---|---|---|---|
| Route and identity | Validate request/JWT and normalize context | Local work | Request logs | healthy base |
| Session access | Up to two sequential SQL `COUNT` queries for an existing session; checkpoint ownership on resume | Shared async SQL pool | No stage timer | confirmed inefficiency |
| Pod authorization | One OpenFGA `CAN_READ` check for a regular collaborative-team user | One remote check per turn | Auth audit, no dedicated latency | expected security cost |
| Runtime binding | Fresh `httpx.AsyncClient`; control plane builds a full team DTO before reading the instance/settings | About 21 control-plane OpenFGA operations plus DB/identity work per turn | No binding-stage budget | [TURN-01](./TURN-01-control-plane-runtime-binding-fanout.md) |
| Model authorization | One OpenFGA `ListObjects` before model routing | One remote lookup per team turn | No dedicated latency | existing [PERF-02](../2026-07-26-observ-02-v3/PERF-02-model-authz-openfga-hot-path.md) |
| Runtime activation | Rebuild runtime/model wrapper/compiled agent; discover MCP tools on a token-scoped cache miss | Per-turn object churn; cold work multiplies by user token and pod | Partial logs only | [TURN-02](./TURN-02-mcp-cold-path-and-cache-scope.md), [TURN-08](./TURN-08-per-turn-runtime-rebuild.md) |
| LLM | Async streaming through shared pool, explicit timeout | Pool max 500 / keepalive 200 in production catalog | Canonical metric for ReAct/Deep, not Graph | healthy base plus [TURN-03](./TURN-03-graph-runtime-observability-and-authz.md) |
| Tool calls | ReAct/Deep recheck OpenFGA on every call; Graph calls tools directly | Security cost grows with tool-call count | Canonical metric/audit only for ReAct/Deep | [TURN-03](./TURN-03-graph-runtime-observability-and-authz.md), [TURN-04](./TURN-04-turn-resource-bounds.md) |
| Token refresh | ~~On a 401, synchronous Keycloak HTTP from an async call path~~ **fixed 2026-08-07** | Could stop the pod event loop for up to 10 seconds | `auth.token_refresh_latency_ms{status}` | [TURN-07](./TURN-07-sync-token-refresh-in-async-path.md) |
| SSE and history | Retain all event payloads, then launch an untracked background write | Memory and pending tasks grow with concurrent/large turns | Turn latency excludes persistence completion | [TURN-05](./TURN-05-sse-buffering-and-history-backpressure.md) |
| Shared capacity | SQL pool defaults to 5 + 10 overflow; Uvicorn concurrency limit is unset | No explicit admission bound at the pod | Pool telemetry exists but no proved envelope | [TURN-06](./TURN-06-admission-and-sql-capacity.md) |

At 200 simultaneous managed turns, the current binding implementation can
generate roughly 4,200 control-plane OpenFGA operations before LLM execution,
in addition to about 200 pod execution checks and 200 model-capability lookups.
This is a static call-budget estimate, not a production latency measurement.

## Findings

| ID | Priority | Verdict | Summary |
|---|---:|---|---|
| TURN-01 | P1 | confirmed | Runtime binding over-fetches a full team projection and fans one turn out to about 21 control-plane ReBAC operations |
| TURN-02 | P1 | needs-load-test | MCP cold discovery is sequential per server, token-scoped, pod-local, and lacks singleflight |
| TURN-03 | P1 | confirmed | Graph bypasses canonical LLM/tool KPI, tool audit, and per-call team authorization |
| TURN-04 | P1 | confirmed | A turn may send 500 history messages, has no default tool-call cap, and ignores the declared parallel-call policy |
| TURN-05 | P2 | needs-load-test | SSE retains the full event stream and launches unbounded fire-and-forget history tasks |
| TURN-06 | P1 | needs-load-test | Admission is unset while checkpoint/history traffic shares a default 15-connection SQL ceiling |
| TURN-07 | P1 | confirmed — fixed 2026-08-07 | Expired-token recovery performs synchronous Keycloak HTTP inside async tool/client paths |
| TURN-08 | P2 | needs-load-test | Runtime activation and ReAct compilation are repeated for every turn |

`confirmed` means static inspection proves the code shape. It does not claim a
measured p95/p99 regression. `needs-load-test` means the scaling mechanism is
established, but the operational impact or safe capacity envelope is not.
`fixed <date>` means the finding has landed a fix — see that dossier's
**Resolution evidence** for what was proven and what still needs a live stack.

## Working protocol for Claude and Codex

1. Work on one dossier and one dedicated GitHub issue at a time.
2. Preserve the security invariant before optimizing: team and capability
   authorization remain fail-closed.
3. Append current evidence and load results to the dossier; do not silently
   replace the original observation.
4. Keep static proof separate from p95/p99 conclusions.
5. Close a finding only when its acceptance criteria, focused tests, quality
   checks, and representative load scenario are recorded under **Resolution
   evidence**.
6. Update the canonical design document when the runtime contract changes.
   Do not create a new RFC merely to restate the implemented design.

## Review verification

Focused correctness suites passed on the reviewed branch:

- `libs/fred-runtime`: 131 tests covering the execution app, Graph
  observability, tool middleware, middleware resource limits, history, MCP
  configuration, token expiry, and user-token refresh;
- `apps/control-plane-backend`: 2 tests covering the managed runtime-binding
  endpoint and selected team capability settings.

These tests establish that the cited paths are live and functionally covered.
They do not assert remote-call counts, absence of event-loop blocking, bounded
memory/task growth, or a concurrency SLO.

## Review limits

This was a source-level audit supported by focused correctness tests. It did
not run a production-like OpenFGA, MCP, PostgreSQL, Keycloak, LLM gateway, or
four-replica load. Therefore no dossier claims a measured SLO violation or a
safe maximum concurrency.
