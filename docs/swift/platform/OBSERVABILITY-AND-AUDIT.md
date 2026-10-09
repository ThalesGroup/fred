# Observability, KPI & Audit Architecture

Audience: architects and security officers (RSSI) reviewing or accepting Fred's logging and
audit posture. For implementation detail (file/line references, phased commits), see
[GitHub issue #2009](https://github.com/ThalesGroup/fred/issues/2009) (`OBSERV-03`) — this
document describes the target state and its guarantees, not the diff to get there.

> Frontend/access-control counterpart: [`REBAC.md`](./REBAC.md) — this document assumes the
> reader already knows Fred's authorization model (Keycloak authenticates, OpenFGA authorizes).

## 1. The problem this solves

Fred previously routed three unrelated kinds of signal through one code path and called all of it
"KPI": platform health, product usage, and security evidence. That conflation made it impossible
to answer, with confidence, questions like *"prove that agent X invoked tool Y for user Z, and
that this record cannot be quietly lost or altered."* This document defines three separated data
streams, each with an explicit purpose, audience, retention model, and privacy boundary.

## 2. The three streams, at a glance

| Stream | Answers | Destination | Audience | Contains identity? |
|---|---|---|---|---|
| **Operational metrics** | Is the platform healthy? | Prometheus, scraped by Google Managed Prometheus, visualized in Grafana | Platform SREs | No — user/session/team identity is structurally excluded |
| **Product analytics** | How is the platform used, by whom, how much? | OpenSearch, queried through Fred's own authorization-scoped API | Org admins, team owners, individual users (each sees only their own scope) | Yes, but access is scoped server-side per viewer |
| **Security & audit trail** | Who did what, when, with what outcome? | Structured log line → the platform's log pipeline (Cloud Logging at C1/C2, sovereign equivalent at C3) | Security/incident response, compliance | Yes with both delegation switches off; with a switch on, runtime, grant and account status events carry only event, outcome and reason (§5) |

A fourth, lower-stakes stream — generic application/debug logging — is covered in §6.

## 3. Stream 1 — Operational metrics (Prometheus / Grafana)

**Purpose.** Answer "is the platform healthy" — latency, error rates, throughput — for the team
operating the infrastructure. Not a product-usage or audit tool.

**What is captured.** A bounded, explicitly-allow-listed set of dimensions per metric: which
tool or route, success/failure/error-code, which model, which agent *type* (the catalog
blueprint — e.g. "customer-support-bot" — not a specific team's configured copy of it), which
pod/service.

**How a service names itself.** The `service` dimension is a lowercase slug, and it is the same
value in this stream and in the log records of §6 — that equality is what lets a log line be
joined to its own metric. A standalone backend declares it in its own `log_setup` /
`build_kpi_writer` calls (`control-plane`, `knowledge-flow`, `rags-services`). An agent pod
declares it as `app.runtime_id` in its `configuration.yaml`, where it must equal the id the
control-plane registers that pod under in `runtime_catalog_sources[].runtime_id`. A pod that
omits it does not start. `app.name` is a display string and is never used as an identifier —
sourcing one from it would put spaces and capitals in a Prometheus label.

**What is structurally excluded — by design, enforced in code, not by operator discipline:**
- User identity (`user_id`), session identity (`session_id`, `exchange_id`).
- Per-call correlation identifiers (`trace_id`, `correlation_id`, `interrupt_id`) — these carry
  no aggregate value for a dashboard and would otherwise let someone with Grafana access pivot
  from an aggregate panel into a specific raw log entry.
- Team identity (`team_id`) and a specific configured agent instance (`agent_instance_id`) — not
  because they are directly personal data, but because "usage by team/agent instance" is a
  product-analytics question with its own authorization-scoped answer (Stream 2) — duplicating it
  here would mean maintaining a second, unsynchronized access-control model for the same fact.

**Retention & access.** Whatever the Prometheus/Grafana deployment's own policy is — no
Fred-specific retention requirement, since nothing identifying reaches this stream.

## 4. Stream 2 — Product analytics (owned by a separate track, referenced here)

Usage questions — active users, conversations per team, top agents by usage, token consumption
per team/user — are answered by Fred's own analytics surface (`/admin/analytics` and related team
and personal dashboards), not by Grafana. This surface resolves the caller's authorization scope
**server-side, before querying**: an org admin sees platform-wide aggregates, a team owner sees
only their own teams, an individual user sees only their own consumption. It is backed by
OpenSearch and — deliberately — carries full identity (including `user_id`) in that store, because
without it the per-viewer scoping in the paragraph above could not be enforced.

This stream is specified and owned by a separate design document (tracked informally as
`OBSERV-02`); this document does not modify it. The only fact this document depends on is
that it exists and must not be broken by changes to Stream 1 or Stream 3.

## 5. Stream 3 — Security & audit trail

**Purpose.** An unambiguous, durable record that a given action was actually taken — the answer to
"prove this happened" for incident response, security review, and compliance.

**What is recorded, per event:**
- The acting principal (human user or service identity), with both delegation switches off (see
  below).
- What was done: an authorization decision (granted/denied) or a tool invocation, identified by a
  stable, finite vocabulary of event names — not free text.
- The outcome: `succeeded`, `failed`, `cancelled`, or `timed_out` (kept distinct — a timeout does
  not prove the target system produced no effect, and collapsing it into "failed" or "succeeded"
  would misrepresent that uncertainty).
- Correlation identifiers (session, exchange, trace) sufficient to relate the event to the rest of
  the platform's telemetry for the same interaction, with both delegation switches off.
- Bounded error information (an error code, an exception class name, an HTTP status) — never a raw
  exception message or stack trace.

**What an agent runtime's events carry, per delegation setting:**
- Both switches off: each event carries the fields its call site passes. Admission and session
  events (`rebac_authorized`, `service_agent_authorized`, `managed_execution_without_team`,
  `direct_execution_forbidden`, `session_owner_mismatch`, `team_binding_mismatch`) name the
  principal, team, agent or session involved. Tool invocation events carry the principal, team,
  session, agent and correlation identifiers. `rebac_denied`, a managed admission refused for a
  missing team permission, carries only outcome `rejected` and reason `permission_refused` in
  either setting.
- A switch on: every runtime event carries only its event name, an outcome and a reason. Admission
  events keep a supplied outcome and reason only when each is a bounded code of lowercase letters
  and underscores; otherwise the outcome is `rejected` for a warning or error, `accepted` for
  anything else, and the reason is the event name. Tool invocation events carry `started`,
  `succeeded`, `failed` or `cancelled` with a bounded reason.
- Grant decisions (`delegation.grant.accepted`, `delegation.grant.rejected`) and account status
  refusals (`authorization.account.refused`, reason `account_suspended` or
  `account_status_unavailable`) carry only an outcome and a reason, whatever the switches. An
  account status refusal at admission produces no `rebac_denied` event.

**What is never recorded, under any circumstance:**
- Full tool arguments or tool results/content.
- Prompts or user messages.
- Document content or attachments.
- Bearer tokens, cookies, authentication headers, signed URLs, or any other secret.
- Raw stack traces or unbounded exception text.
- Directly identifying data (name, email) where an opaque platform identifier already suffices.

**A proposal is not an action.** A tool call the model proposed but that was refused by
human-in-the-loop confirmation never produces an audit event. The audit trail records what Fred
actually did, not what a model suggested. A call that passes confirmation and is then refused by
the per-tool authorization recheck produces `agent.tool.invocation.started` followed by
`agent.tool.invocation.completed` with outcome `failed`: reason `authority_lost` in a delegated
run; otherwise reason `AuthorizationError` with a switch on, or error code and exception type
`AuthorizationError` beside the identifiers above with both switches off.

**Known gap: relation writes.** `authz.relation.granted`, written by the shared relationship engine
on every relation write, and `authz.relation.revoked` name the acting user and the relation's
subject and resource whatever the switches. The engine also writes `authz.relation.granted` inside
an agent runtime when a person's first run in their personal space creates their own membership.
The control plane's `platform.announcement.*` and `team_admin.charter.accepted` events name the
acting user. Bringing these events to the bounded shape is left for a later change.

**Where it goes, and why this is the harder design question.** Fred emits this as a structured,
single-line JSON entry through its normal logging output — it never makes a direct, synchronous
network call to a cloud logging service as part of executing a request (that would make an
external outage a Fred outage). What happens to that JSON line downstream is a deployment
concern, and it is **not identical across classification levels**:

- At C1 and C2 (public/restricted GKE on GCP), the platform's standard Kubernetes log collection
  forwards pod output to Cloud Logging. Structured JSON output means these entries can, in
  principle, be selected and routed to a dedicated, access-restricted, long-retention destination
  independently of routine application noise — this is an infrastructure/IAM configuration
  decision made by the platform team operating the cluster, not something Fred's code controls or
  assumes.
- At C3, the target hosting platform is a sovereign cloud, not GCP — there is no guarantee an
  equivalent "Cloud Logging" API exists at all. The one component the deployment pattern commits
  to keeping identical at every classification level is the platform's own OpenSearch (part of
  the shared stateful backbone, deployed the same way everywhere). Fred's audit trail is therefore
  designed to be equally at home landing in OpenSearch as in a cloud provider's log service —
  **the guarantee Fred's code provides is a correctly-shaped, privacy-safe, structured event; the
  guarantee of where it durably lives, for how long, and who can read it, is a deployment-level
  responsibility that must be established per classification level, not assumed from the C1
  reference sample.**

**What Fred does not claim.** Fred does not implement a tamper-proof storage layer itself (no
custom WORM store, no in-app immutability guarantee). Tamper-evidence and long-term integrity are
properties of wherever the platform team routes and locks these events downstream (a locked log
bucket, an access-restricted OpenSearch index with its own retention policy, or equivalent) — a
compromised application pod should not be able to rewrite history, which is precisely why this is
an infrastructure guarantee, not an application one.

## 6. Generic application / diagnostic logs

Python APIs select `app.log_format: json | text` explicitly. Chart reference values
select JSON; omitted settings and local examples select readable text. JSON stdout
uses `severity`, `message`, creation-time `timestamp` (seconds/nanoseconds), `logger`,
existing stable `service`, API role, source location and structural category. Context
and safe event properties are top-level JSON fields; collisions cannot replace core
metadata or bound identity. The optional generic store keeps its existing DTO shape.
Readable text has no terminal-width wrapping and disables colors when redirected.
Audit output remains independently formatted and excluded from generic context/store
processing. Dependency warnings/errors are console-only to avoid sink recursion.
Collector timestamp/severity recognition requires a rollout canary.

Existing standard-library `%s`, `%d` and named-placeholder log calls remain supported
in both output formats. They can also supply `extra={...}` structured properties,
allowing gradual migration without rewriting every message or switching to f-strings.


Ordinary application logs (startup messages, warnings, day-to-day diagnostics) are the lowest-
sensitivity, highest-volume stream. They are stored in OpenSearch alongside — but in a separate
index from — product analytics, with no long-retention requirement. Their diagnostic value
decreases over time; they are not an audit or compliance artifact and should never be treated as
one.

This stream carries no content (§7). Fred does not expose its own query surface for these logs —
there is no Log Console UI and no `/logs/query` endpoint or agent tool. Consultation and
exploration happen directly against the backing OpenSearch index via **OpenSearch Dashboards**,
outside Fred's authorization model; that index is a meaningfully different exposure than "an
individual user's own data," so access to Dashboards itself is an infrastructure/deployment
concern, not something Fred's API mediates. The raw OpenSearch Ops surface this stream sits next
to (cluster health, indices, mappings, shards) is a separate, still-Fred-exposed admin surface and
requires `CAN_OBSERVE_PLATFORM` — the same platform-wide observation capability that gates
Stream 2's control-plane Analytics presets (§4) — enforced server-side, not only hidden behind a
frontend route guard.

Each event carries a closed, structurally-derived `category` (`application` or `kpi`) — never
inferred from message text (a message that happens to contain the literal string `"[KPI]"` or
`"[AUDIT]"` does not become that category; only an event actually emitted on the reserved `KPI`
logger does). Real audit events (Stream 3) never appear in this store at all — enforced doubly:
`fred.security.audit` does not propagate to the root logger, and the store's ingestion handler
independently drops any record from that logger by name.

With either delegation switch on, request access lines carry only a neutral event, outcome, method
and status; the request route is available through the KPI `route` dimension (§3).

## 7. Data protection summary

| Field category | Example fields | Where it may appear |
|---|---|---|
| Directly identifying | user email, full name | **Nowhere** — Fred uses opaque platform identifiers everywhere an identity reference is needed |
| Pseudonymous / opaque identity | `user_id`, `session_id`, `team_id` | Product analytics (Stream 2, access-scoped) and the audit trail (Stream 3, per delegation setting as §5 details) — never in operational metrics (Stream 1) |
| Content | prompts, tool arguments/results, documents, attachments | **Nowhere** in any observability or audit stream — content lives only in the product's own storage, under the product's own access control. One deliberate, default-off local exception: `observability.langfuse.capture_content` (see below) |
| Secrets | tokens, cookies, signed URLs | **Nowhere**, ever |
| Technical/bounded | tool name, error code, HTTP status, model name | All streams as relevant — none of this is personal data |

**Practical reading for an RSSI:** the only stream that intentionally carries user identity is
Stream 2 (product analytics, itself access-scoped per viewer) and Stream 3 (the audit trail, whose
entire purpose is to attribute an action to a principal). With a delegation switch on, runtime,
grant and account status audit events carry no identity; relation-write events still do (§5). Stream 1
(what a platform-wide Grafana audience can see) is designed to never carry it at all — not
filtered as an afterthought, but structurally excluded before a metric is ever labeled.

### 7.1 The one content exception: Langfuse local debugging (2026-08-20)

Tracing (the optional `tracer: langfuse` backend) is the one place where a developer can
deliberately turn the content exclusion off, and only for a Langfuse they run themselves. The
switch is `observability.langfuse.capture_content` in `configuration.yaml`, overridable per-run by
the `LANGFUSE_CAPTURE_CONTENT` env var. It is **off by default**, and enabling it exports prompts,
model answers, and tool arguments/results to Langfuse.

Why this is bounded rather than a hole in the rule:

- **Default-off and structurally enforced.** The switch is exposed as `Tracer.captures_content`
  (`libs/fred-core/fred_core/portable/observability.py`). Every call site checks it before
  building a payload, and `Span.set_io` drops the payload again if it is off — so a call site that
  forgets the check still cannot leak. `Tracer` and `LoggingTracer` both answer `False`
  permanently, which is what keeps the generic app-log store (§6) and the audit trail (§5) content-
  free no matter what tracing does.
- **Never the log store.** `LoggingTracer` records payload *sizes* only, never the payload — the
  same rule `tracing_kpi.py` has followed since issue #2009 (2026-07-18).
- **Never Prometheus.** Content and identity both stay out of Stream 1; this exception adds no
  metric and no label (§3's allow-list is untouched).
- **Loud at startup.** The pod logs a warning naming the destination host whenever capture is on,
  so an operator cannot leave it enabled unnoticed.

Enabling it on a shared or production deployment exports user conversations to a system that does
not enforce Fred's authorization model. It is a laptop-only debugging affordance, not a supported
deployment mode.

Independently of content, Langfuse traces do carry the pseudonymous identity set (`session_id`,
`user_id`, `team_id`) in Langfuse's native trace fields — that is the row-2 category above, and it
is what makes per-conversation and per-user trace analysis possible at all.

## 8. Cross-classification portability (C1 / C2 / C3)

Per the deployment pattern's own classification model, three things change with classification —
secrets source, network segmentation, and hosting/sovereignty (C3 = sovereign cloud, not GCP) —
and nothing else does. This observability architecture is designed against that constraint:

- Stream 1 (Prometheus/Grafana) and Stream 4 (OpenSearch) use only platform-native mechanisms
  present at every level.
- Stream 3 (audit) is designed so its correctness (privacy-safe, correctly-shaped JSON) does not
  depend on any GCP-specific feature — only its *durable delivery target* changes per platform,
  which is expected and tracked as a deployment responsibility, not a code branch.
- Stream 2 is unaffected by classification — it is Fred's own API surface, backed by the
  Foundation-layer OpenSearch present identically everywhere.

## 9. Maturity — target vs. what is true today

| Guarantee | Status |
|---|---|
| Operational metrics exclude direct identity | **True today** — enforced in code |
| Operational metrics exclude all per-call correlation and team/agent-instance identifiers | **True today** — `PROMETHEUS_ALLOWED_LABELS` is an explicit allow-list; a new dim needs a deliberate decision to become a label |
| Product analytics scoped per viewer via authorization | **True today**, shipped |
| Every tool invocation produces an audit-channel event | **Shared boundary for ReAct, Deep and Graph.** `runtime_support.tool_execution.ToolExecution` owns authorization rechecks, `agent.tool.invocation.{started,completed}` audit events and canonical tool KPIs. ReAct/Deep enter through `ToolObservabilityMiddleware`; Graph enters through both `NodeContext.invoke_tool` and `invoke_runtime_tool`. Returned error artifacts, raised failures and cancellation remain distinct. Capability HITL uses shared approval rules across all three runtimes; calls refused at approval do not execute or emit invocation audits/KPIs, while a call refused by the per-tool recheck emits `started` then `failed` (§5). The audit destination/retention guarantee remains a deployment responsibility. |
| Every runtime emits canonical LLM/tool latency KPIs | **Tools: shared across ReAct, Deep and Graph. Models: still partial.** All three tool paths emit `agent.tool_latency_ms` and `agent.tool_failed_total` through `ToolExecution`; Graph no longer emits a duplicate generic tool-phase timer. ReAct/Deep emit `llm.call_latency_ms`; Graph model phases still use `app.phase_latency_ms`. |
| Audit records are valid structured JSON on the log output | **True today** |
| Generic logs land in durable storage, explorable via OpenSearch Dashboards | **True today** where a service's `storage.log_store` is set to `opensearch` — still `RamLogStore` (in-memory, lost on restart) where it isn't; flipping the C1 reference deployment's config is a separate, infra-only follow-up |
| Generic logs contain no prompt/response/tool-argument/document content | **True today** — fixed 2026-07-18 (issue #2009); several logger call sites (`tracing_kpi.py`, `react_runtime.py`, the vectorization pipeline) previously logged raw content previews into this store |
| Fred exposes no log-query surface of its own (no Log Console UI, no `/logs/query` endpoint, no `logs.query` agent tool) | **True today** — reversed 2026-07-18: the Log Console UI, its backend endpoint, and the `logs.query` built-in agent tool (all shipped earlier the same day under issue #2009) were removed the same day in favor of OpenSearch Dashboards as the sole log exploration surface |
| The remaining OpenSearch Ops surface (cluster health, indices, mappings, shards) requires `CAN_OBSERVE_PLATFORM` server-side | **True today** — fixed 2026-07-18 (issue #2009); previously gated only by the frontend route |
| Generic-log `category` is a closed, structurally-derived field | **True today** — fixed 2026-07-18 (issue #2009); previously only a decorative `[KPI]`-text convention with no queryable field |
| A KPI/log sink outage cannot fail or stall a business request | **True today** — fixed 2026-07-18 (issue #2009); writes are now fail-open with a bounded queue and circuit breaker in front of the OpenSearch-backed stores |
| A successfully ingested tabular (CSV→Parquet) artifact leaves a positive confirmation in generic logs | **True today** — fixed 2026-07-19; `TabularProcessor._persist_parquet_artifact` (knowledge-flow-backend) uploaded the Parquet artifact to content storage without logging anything on success, so an operator diagnosing the SQL-agent/DuckDB ingestion path had no stdout/OpenSearch evidence that ingestion actually produced a queryable dataset — only a `logger.exception` on failure. Now emits one `[TABULAR] document_uid=... object_key=... rows=... size_bytes=... format=... compression=...` line per artifact, mirroring the tag already used for query execution in `TabularService.query_read`. No content: only opaque identifiers and volume metrics already exposed elsewhere in the same log. |
| Downstream retention/access/integrity for the audit trail | **Deployment responsibility, not yet established at any classification level** — requires action by whoever operates the target cluster, independent of Fred's own code |

This table is the honest current state as of 2026-07-26. It should be updated as each guarantee
moves from target to true, and treated as the canonical status reference for this topic — do not
let a parallel status document drift from it.

**Known follow-up, deliberately not done in issue #2009 (mechanical-scope discipline, same
reasoning as `26ae63e6`'s note on the 26 `[AUTH]` renames):** `opensearch_kpi_store.py`'s
`query()` still logs four `"[KPI][QUERY] ..."` lines on its own module logger (not the reserved
`KPI` logger) — a decorative reuse of the same tag `26ae63e6` stopped elsewhere. Not a content or
authorization gap (the values logged are query filter dims already carried in the KPI store's own
identity fields, and `category` resolves correctly to `application` regardless of the tag text) —
just hygiene. Renaming to a non-reserved tag (e.g. `[KPI-STORE]`) or dropping the bracket entirely
is a good follow-up.

## Authentication operational signals

The API security startup hook installs an optional observer for the shared M2M
provider. Fred exports its collectors through the existing default Prometheus
registry. No metrics dependency is added to fred-pod.

| Metric | Meaning |
| --- | --- |
| `fred_auth_m2m_request_seconds` | Actual IAM token attempts including response validation; operation initial/renewal and outcomes success/error/cancelled. Histogram `_count` gives request/error rates. |
| `fred_auth_m2m_acquire_seconds` | Caller wait including cache, lock and IAM; same outcomes. A delegated request records one, plus one per 401 renewal; the retry reuses the renewed token. |
| `fred_auth_m2m_cache_total` | Decisions hit/miss/shared_refresh; not mutually exclusive request outcomes. |
| `fred_auth_delegation_decisions_total` | Grant admission accepted/rejected, with the bounded reasons of the existing audit events. Not downstream authorization or execution success. |

These are operational collectors, not product analytics. Labels contain no URL,
client, user, team, token or run ID. Use scrape job/instance to locate the source.
`initial` means this provider has never acquired a token; `renewal` means it is
replacing a previously acquired token. Each provider/replica has its own cache;
a new process starts with an initial acquisition. A cache miss is not necessarily
an IAM call: a concurrent caller may wait for another caller's renewal.

### Using the dashboard

Open **Fred / Application KPIs** in local Docker Grafana (default
http://localhost:3002). From deployment-factory, `make grafana-up` starts local
Prometheus and Grafana. Use matching Fred/factory branches and restart the three
Fred APIs after configuration changes. The local exporters listen on 0.0.0.0 so
Docker can scrape them through host.docker.internal; keep ports 9000, 9222, 9111
and worker 9112 on a trusted development network. Check Prometheus **Targets**
(default http://localhost:9090/targets) before diagnosing an empty dashboard.

Docker and GCP provision the same application dashboard JSON and datasource UID;
Docker's `gmp` UID points to local Prometheus, GCP's to its managed query service.
The base Docker stack does not start Grafana automatically. The local command
above is sufficient; the full extended stack is not required. An already-running
Grafana must be recreated through its Make target to load new volume mounts.

- **IAM workload token requests / s**: initial acquisition versus renewal, success
  versus error/cancellation. No new request during cache reuse is expected.
- **IAM request p95**: time spent obtaining/validating a token. **Caller wait p95**
  also includes lock waiting; it can rise when concurrent callers share a refresh.
- **Cache decisions**: hit, miss, shared refresh. These are events, not
  mutually exclusive outcomes; do not sum them as a request count.
- **Delegation decisions**: grant admission only, not a guarantee of downstream
  authorization or execution success.

Known series start at zero. Missing series are not proof of zero failures: verify
scrape `up`, the matching application build and the time window first. Rate panels
need at least two scrapes; p95 has no useful value without observations. Histograms
are bucket-based estimates, not exact request timings. For sparse renewal tests,
use `increase(fred_auth_m2m_request_seconds_count{operation="renewal"}[10m])`;
for an exact single-run comparison, record raw counter values before/after,
ensuring there was no process restart or other traffic.

### Keeping this documentation current

The collector declarations in `fred_core/security/auth_metrics.py` are the source
of truth for names, labels and histogram buckets. Keep this guide focused on
meaning, scope and operations; do not duplicate buckets or every Prometheus
`_bucket`/`_sum`/`_count` series in prose. When changing the collectors, update the
shared dashboard and run `make check-auth-dashboard` in deployment-factory
(`SWIFT_SRC=/path/to/fred` if needed). It checks authentication query names and
aggregation labels against the source without importing applications. This is a
static contract check, not a PromQL execution or live scrape check. Run it during
paired repository reviews; deployment-factory currently has no CI workflow that
automatically enforces it. Runtime tests verify initial acquisition, cache reuse,
renewal and acquisition-failure observations.

Runtime user refresh already emits `auth.token_refresh_latency_ms` through the
KPI writer. Browser refresh contacts the IAM directly and only warns in the
browser console when a refresh times out or fails, without token contents or the
rejection value; there is no central browser/IAM telemetry.
These counters do not cover all JWT rejection paths or count auth-related run
failures. A short chat after expiry does not prove renewal during a long run.

### Execution errors and support references

Unhandled runtime errors return a fixed phase-specific explanation and a random
support reference to the UI. Search `error_ref` in the agent pod logs for the same
reference. The diagnostic includes exception types and code locations (file basename,
line, function), including bounded exception chains/groups. It deliberately omits
exception messages, URLs, variables and source lines, which may contain credentials
or delegated identities. The reference is per error, not a user/session identifier.

## Deferred proposal: platform-admin authentication health

Deferred by the developer on 2026-09-24 to a separate issue/PR; not part of the
current authentication-metrics implementation.

A read-only admin card could show, over a selectable recent window: reporting
replicas and scrape failures, initial M2M acquisitions versus renewals, failed
attempts, IAM latency p95, delegation admission outcomes and data freshness.
Allow component/replica breakdown and a copyable diagnostic summary without
credentials or user identities. Failed attempts do not imply failed user runs;
missing data and idle traffic must not be presented as healthy operation.

Architecture: the frontend calls a platform-admin-only Control Plane endpoint;
Control Plane executes fixed, bounded queries against Prometheus or the managed
metrics query service. Aggregate across all replicas; do not poll individual
Fred pods or query Grafana. Keep metrics credentials server-side, use timeouts
and bounded refresh/caching, and never expose an unrestricted PromQL proxy.

Start with observed replica counts and scrape failures. Expected-versus-reporting
coverage needs reliable deployment discovery and is optional follow-up scope.
Browser renewal telemetry remains a separate gap. Before implementation, confirm
the deployment's query endpoint, read credentials and component labels; test
permissions, multi-replica aggregation, restarts and missing/stale data.

## Restricted web research activity

Native web research requires a separate runtime PostgreSQL product activity table.
It stores the opaque user/team/agent/session/correlation identifiers, submitted
query or public URL (without query parameters/fragments), outcome, duration and
result count. It stores neither snippets nor downloaded page bodies. Ordinary
logs, Prometheus labels and security audit remain content-free. Platform operators
(`CAN_MANAGE_PLATFORM`) can read unexpired records; user administrators
(`CAN_ADMINISTER_USERS`) can erase them. The default retention is 30 days,
configurable from 1 to 365; reads exclude expired rows and a periodic worker
physically purges them even after feature disablement.

Deleting or suspending an account does not erase this activity: it stays a
security trace until expiry, like conversation history. Erasure is an explicit
administrator action for a right-to-erasure request:
`DELETE /agents/web-research/activity/users/{user_id}` on Fred Agents
(`CAN_ADMINISTER_USERS`) deletes every record of that user and returns
`{"deleted": <count>}`; the call is itself audited (`web_research.activity.erased`).
It does not block later use: an operation running during the call, or a later
one by the same user, is recorded normally and expires with the retention.
Activation requires the activity store and operator approval of query collection.
See [deployment and migration instructions](../ops/migrations/2980-native-web-research.md).

## LLM streaming incident diagnosis

The shared ReAct/Deep model middleware, including native Deep children, emits
`llm_call_started` and `llm_call_completed` diagnostic records. Their generated
`llm_call_id` links one invocation across logs and spans. A failed invocation's
safe snapshot also appears in `execution_error.llm_failures`, alongside the
existing support `error_ref`. Exception causes/groups are bounded; a truncation
flag means the list is incomplete. No prompt, answer, tool value or raw exception
message is added. Upstream `x-request-id` and `apim-request-id` are restricted to
128 ASCII identifier characters and omitted when delegation is enabled.

To investigate in OpenSearch Dashboards (field prefix depends on ingestion):

1. Search `extra.error_ref: "<support-reference>"`; read `extra.llm_failures`.
2. Search `extra.llm_call_id: "<call-id>"` for that invocation's start/end.
   Native model/parent run IDs help distinguish concurrent child branches; absent
   ancestry is unknown. Each Fred retry attempt has its own call ID.
3. Compare effective settings, model, pod/service and dependency versions with a
   successful run. `llm_model_configuration`, `llm_client_versions` and `[NET]`
   initialization/mismatch logs describe the wrapper and shared pool. Settings
   are allow-listed; do not enable generic HTTP body/header debug logging.
4. Where present and permitted, give the upstream request ID and incident time
   to gateway/provider operators. HTTP 200 only proves headers were received;
   the body may still stall or terminate early.

The runtime Grafana dashboard uses these additive metrics (dots become
underscores in Prometheus):

| Metric | Meaning |
|---|---|
| `llm.calls_total` | Terminal invocations by model, `llm_role` (root/child), status and bounded error code |
| `llm.active_calls` | Instantaneous active invocations per process/model/role; sum across replicas, never across time |
| `llm.first_chunk_ms` | Time from the observed invocation start to its first LangChain chunk callback |
| `llm.max_chunk_gap_ms` | Largest interval between observed callbacks; absent with fewer than two callbacks |
| `llm.terminal_silence_ms` | Time since the last callback at termination; absent if no callback occurred |
| `llm.call_latency_ms` | Existing total invocation latency signal, still emitted on success/error/cancellation |

Operational labels exclude all call/run/provider IDs and user/session/team
identity. The new timing histograms have finite buckets through 30 minutes;
missing observations remain missing, not zero. Diagnostic records also contain
request message/tool/character counts, available provider usage, elapsed time,
response-header arrival time/status and bounded timeout attributes.

Call and chunk timings use the model handler's entry and exit timestamps,
excluding this middleware's sizing, logging and trace setup/teardown. This remains
a client-side handler measurement, including SDK processing and downstream
middleware, rather than a measurement of provider compute time alone.

`observed_chunks` counts callbacks, including empty, tool and reasoning deltas
and library-generated final markers. It is neither a token count nor a count of
network packets. `sdk_chunks_received` is a separate exception-provided count.
`stream_idle_timeout` identifies the chunk watchdog; `read_timeout`,
`connect_timeout`, `write_timeout`, `pool_timeout`, `remote_protocol_error`,
`connection_error`, `rate_limited`, `provider_http_error`, `cancelled` and
`unknown` distinguish other outcomes. An internal read cancellation caused by a
chunk watchdog is reported as a timeout, not as a user cancellation.

Compare the elapsed lifetime and terminal silence with gateway policies. A
repeatable total lifetime suggests an absolute deadline; repeatable silence
suggests an idle limit. Neither proves attribution. Correlate with existing
`event_loop_lag_ms`, CPU and memory signals: a delayed local event loop can also
delay observations. The sampler can miss short stalls. Callback timing does not
observe raw keepalives or SDK-filtered events.

Coverage is the shared ReAct/Deep model boundary, not all provider billing:
independent Deep summarization calls, arbitrary capability-internal LLM calls
and Graph paths outside that middleware are excluded. Abrupt process death may
leave a start without a terminal record. Telemetry is best-effort through existing
sinks. This instrumentation does not change timeout, retry or concurrency policy.
