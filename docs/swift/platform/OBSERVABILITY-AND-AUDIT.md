# Observability, KPI & Audit Architecture

Audience: architects and security officers (RSSI) reviewing or accepting Fred's logging and
audit posture. For implementation detail (file/line references, phased commits), see the
tracking GitHub issue linked from `OBSERV-03` in `docs/swift/data/id-legend.yaml` — this document
describes the target state and its guarantees, not the diff to get there.

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

This stream is specified and owned by a separate design document (`OBSERV-02` in
`id-legend.yaml`); this document does not modify it. The only fact this document depends on is
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
requires `CAN_OBSERVE_PLATFORM` — the same platform-wide observation capability Stream 2's
`view_global` branch already requires (§4) — enforced server-side, not only hidden behind a
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
| Content | prompts, tool arguments/results, documents, attachments | **Nowhere** in any observability or audit stream — content lives only in the product's own storage, under the product's own access control |
| Secrets | tokens, cookies, signed URLs | **Nowhere**, ever |
| Technical/bounded | tool name, error code, HTTP status, model name | All streams as relevant — none of this is personal data |

**Practical reading for an RSSI:** the only stream that intentionally carries user identity is
Stream 2 (product analytics, itself access-scoped per viewer) and Stream 3 (the audit trail, whose
entire purpose is to attribute an action to a principal). Stream 1 (what a platform-wide Grafana
audience can see) is designed to never carry it at all — not filtered as an afterthought, but
structurally excluded before a metric is ever labeled.

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
| Every tool invocation produces an audit-channel event | **True today** — `agent.tool.invocation.{started,completed}` emitted on the security/audit logger for every actually-executed tool call; the pod-local ring buffer backing `/agents/audit-events` remains scoped to authz decisions and is not the durability guarantee (see the row below). **Gap closed 2026-07-18 (issue #2011):** this guarantee was true for MCP-catalog tools only — `ContextAwareTool` (`mcp_toolkit.py`) was the sole emitter of this event and of the `agent.tool_latency_ms`/`agent.tool_failed_total` KPIs, and capability-native tools (e.g. `DocumentAccessCapability`'s `search_documents_using_vectorization`) never passed through it, so they produced neither signal. Both are now emitted by `ToolObservabilityMiddleware` (`fred_runtime/react/middleware/tool_observability.py`), which wraps every tool call — MCP-catalog and capability-native alike — via `AgentMiddleware.awrap_tool_call`, the one chokepoint every tool call goes through regardless of source. `ContextAwareTool` no longer emits either signal itself (would double-count MCP calls otherwise) but is unchanged for context injection, MCP content normalization, and HTTP-status error handling. |
| Audit records are valid structured JSON on the log output | **True today** |
| Generic logs land in durable storage, explorable via OpenSearch Dashboards | **True today** where a service's `storage.log_store` is set to `opensearch` — still `RamLogStore` (in-memory, lost on restart) where it isn't; flipping the C1 reference deployment's config is a separate, infra-only follow-up |
| Generic logs contain no prompt/response/tool-argument/document content | **True today** — fixed 2026-07-18 (issue #2009); several logger call sites (`tracing_kpi.py`, `react_runtime.py`, the vectorization pipeline) previously logged raw content previews into this store |
| Fred exposes no log-query surface of its own (no Log Console UI, no `/logs/query` endpoint, no `logs.query` agent tool) | **True today** — reversed 2026-07-18: the Log Console UI, its backend endpoint, and the `logs.query` built-in agent tool (all shipped earlier the same day under issue #2009) were removed the same day in favor of OpenSearch Dashboards as the sole log exploration surface |
| The remaining OpenSearch Ops surface (cluster health, indices, mappings, shards) requires `CAN_OBSERVE_PLATFORM` server-side | **True today** — fixed 2026-07-18 (issue #2009); previously gated only by the frontend route |
| Generic-log `category` is a closed, structurally-derived field | **True today** — fixed 2026-07-18 (issue #2009); previously only a decorative `[KPI]`-text convention with no queryable field |
| A KPI/log sink outage cannot fail or stall a business request | **True today** — fixed 2026-07-18 (issue #2009); writes are now fail-open with a bounded queue and circuit breaker in front of the OpenSearch-backed stores |
| Downstream retention/access/integrity for the audit trail | **Deployment responsibility, not yet established at any classification level** — requires action by whoever operates the target cluster, independent of Fred's own code |

This table is the honest current state as of 2026-07-18. It should be updated as each guarantee
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
