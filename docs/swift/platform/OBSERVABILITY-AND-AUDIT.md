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
| **Security & audit trail** | Who did what, when, with what outcome? | Structured log line → the platform's log pipeline (Cloud Logging at C1/C2, sovereign equivalent at C3) | Security/incident response, compliance | Yes — this is its entire purpose |

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
- Per-call correlation identifiers (`trace_id`, `correlation_id`, `checkpoint_id`) — these carry
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
- The acting principal (human user or service identity).
- What was done: an authorization decision (granted/denied) or a tool invocation, identified by a
  stable, finite vocabulary of event names — not free text.
- The outcome: `succeeded`, `failed`, `cancelled`, or `timed_out` (kept distinct — a timeout does
  not prove the target system produced no effect, and collapsing it into "failed" or "succeeded"
  would misrepresent that uncertainty).
- Correlation identifiers (session, exchange, trace) sufficient to relate the event to the rest of
  the platform's telemetry for the same interaction.
- Bounded error information (an error code, an exception class name, an HTTP status) — never a raw
  exception message or stack trace.

**What is never recorded, under any circumstance:**
- Full tool arguments or tool results/content.
- Prompts or user messages.
- Document content or attachments.
- Bearer tokens, cookies, authentication headers, signed URLs, or any other secret.
- Raw stack traces or unbounded exception text.
- Directly identifying data (name, email) where an opaque platform identifier already suffices.

**A proposal is not an action.** A tool call the model proposed but that was refused — by
human-in-the-loop confirmation or by an authorization check — before execution never produces an
audit event. The audit trail records what Fred actually did, not what a model suggested.

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

## 7. Data protection summary

| Field category | Example fields | Where it may appear |
|---|---|---|
| Directly identifying | user email, full name | **Nowhere** — Fred uses opaque platform identifiers everywhere an identity reference is needed |
| Pseudonymous / opaque identity | `user_id`, `session_id`, `team_id` | Product analytics (Stream 2, access-scoped) and the audit trail (Stream 3) — never in operational metrics (Stream 1) |
| Content | prompts, tool arguments/results, documents, attachments | **Nowhere** in any observability or audit stream — content lives only in the product's own storage, under the product's own access control. One deliberate, default-off local exception: `observability.langfuse.capture_content` (see below) |
| Secrets | tokens, cookies, signed URLs | **Nowhere**, ever |
| Technical/bounded | tool name, error code, HTTP status, model name | All streams as relevant — none of this is personal data |

**Practical reading for an RSSI:** the only stream that intentionally carries user identity is
Stream 2 (product analytics, itself access-scoped per viewer) and Stream 3 (the audit trail, whose
entire purpose is to attribute an action to a principal). Stream 1 (what a platform-wide Grafana
audience can see) is designed to never carry it at all — not filtered as an afterthought, but
structurally excluded before a metric is ever labeled.

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
| Every tool invocation produces an audit-channel event | **Partial today — ReAct/Deep only.** `ToolObservabilityMiddleware` emits `agent.tool.invocation.{started,completed,failed}` for MCP-catalog and capability-native calls that pass through the ReAct/Deep middleware frame. Graph runtime tool nodes invoke tools directly and currently bypass this audit boundary. The pod-local ring buffer backing `/agents/audit-events` remains scoped to authz decisions and is not the durability guarantee. See [TURN-03](../reviews/performance/2026-07-26-agent-turn-core/TURN-03-graph-runtime-observability-and-authz.md). |
| Every runtime emits canonical LLM/tool latency KPIs | **Partial today — ReAct/Deep only.** Their middleware emits `llm.call_latency_ms` and `agent.tool_latency_ms`. Graph measures model phases with generic `app.phase_latency_ms` and does not emit the canonical tool metric, so cross-runtime latency dashboards are incomplete. See [TURN-03](../reviews/performance/2026-07-26-agent-turn-core/TURN-03-graph-runtime-observability-and-authz.md). |
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
| `fred_auth_m2m_acquire_seconds` | Caller wait including cache, lock and IAM; same outcomes. |
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
KPI writer. Browser refresh contacts the IAM directly: its console event
`browser_token_refresh` reports refreshed/reused/error/timeout/superseded and
`duration_ms`, without token contents. This is browser-local evidence, not central
production telemetry. Central browser/IAM event collection remains separate work.
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
