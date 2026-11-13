# 8. Operations

## Deployment and configuration

The deployment factory owns the local k3d instance values and infrastructure;
Fred supplies the application chart and image build. Helm combines the chart
defaults with the instance values, including the Control Plane's model sources
and each runtime's credential references. The
[operations reference](A3-manager-operations.md) and
[model reference](A13-models.md#deployment-evidence) identify the deployment inputs.
The frontend forwards `/control-plane/v1` to port 8222.

Rust configuration is validated against its generated schema. Credentials are
references to Secrets, never literal values in application configuration.
`control-plane serve` supervises HTTP, original-storage cleanup, the processing
outbox and lifecycle work in one process. Knowledge Flow runs its Temporal worker.
There is no separate `control-plane worker` command in this runtime.

Model governance and credential provisioning have different lifetimes. The
organization Owner changes permitted models and defaults through Control Plane;
deployment supplies approved destinations and local credentials to the workloads.
Changing a policy does not provision a missing credential. Credentials injected
as environment variables require a workload restart after Secret rotation;
the [rotation contract](A13-models.md#deployment-evidence) explains ordering and
the limits for turns already in progress.

## Ingestion preparation

The Control Plane deployment exports the processing contract from the built worker
image. Buckets, service identities, OpenSearch roles and the search pipeline belong
to the infrastructure (locally, the factory's `k3d/values.yaml`), not to the
application chart. Each organization's corpus is the index
`<manager_processing.vector_store.index>-<organization id>`, created by the worker at
that organization's first indexing. Roles therefore grant this prefix: writes and
index creation to the worker, reads to the API. The local profile grants
`document-vectors-*` and `weaver-kpi`: Swift can share the OpenSearch instance, never
these indexes.

## PostgreSQL ownership

One database contains four isolated schemas. Control Plane owns `control_plane`
(tables, functions, triggers and SQLx history) and `cp_read` (read contracts).
Knowledge Flow owns `knowledge`; Agent Pod owns `runtime`, including Alembic
history and checkpoints. Their logins are `fred_cp`, `fred_kf`, `fred_runtime`;
`fred_monitor` reads only its platform-role view. Consumers receive SELECT through
reader groups and have no access to the Control Plane schema. `public` is closed.

An administrator runs the deployment-owned bootstrap before schema initialization.
It creates roles, schemas and the vector extension without passwords. Deployment
supplies separate credentials through Secrets, then runs Control Plane SQLx,
runtime migrations, and starts applications, in that order. The optional chart
bootstrap hook is disabled by default: managed installations have their DBA run
the [bootstrap procedure](../../deploy/postgres/README.md). Applications never
receive role-administration privileges. The first installation with this layout
requires a fresh database; no conversion of an old `public` database is attempted.

## Schema initialization and recovery

Weaver Control Plane installs its complete schema on a fresh database. The
pre-install/pre-upgrade initialization Job is repeatable when the schema matches;
it refuses an incompatible database without transforming or resetting data.
API startup verifies the schema and never modifies it. See the
[SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue) and
[initialization procedure](A3-manager-operations.md#sqlx-schema-initialization).

SQL and its matching object namespace form one backup unit. Restore suspends
uploads and cleanup until both are consistent. Application deployment does not
migrate existing Knowledge Flow documents or rename persisted resources.

The Rust ingestion profile does not support application data reset. The reset
helper rejects this configuration before mutation; its Swift erasure contract
must not be widened to include Rust document resources. Recreating a disposable
secondary installation is a separate, explicitly authorized deployment operation.

## Consumption, observation and technical health

Each figure has one authoritative source. The registry in Control Plane's
PostgreSQL records exactly and idempotently how much was consumed or owned,
by whom and for which resource. Tokens belong to this registry. If a figure will
ever be compared with a limit, a bill or a quota, it belongs in the registry.
OpenSearch serves agent-behavior observation, where occasional loss is acceptable.
Application logs are not among these figures: every process writes them to stdout
and the platform's collector routes them, as described under Logs and lifecycle.
Prometheus and OpenTelemetry serve technical health and operations.

The runtime reports consumption in its own name, using its workload identity.
Control Plane derives the person, space and agent from the session metadata.
The consumption journal records one row per offer consumed in a report. An entire
report is written atomically; the report (one run), identified by `Idempotency-Key`,
is the unit of idempotency. Replaying the same report does not count twice; any
change to its session, exchange, occurrence time, offers or counters conflicts.
A turn interrupted for human validation produces several reports, and its
consumption is the sum of those reports. Provenance survives retirement or purge.
Embedded Ralph submits one report per managed turn with at least one decoded
model response, through the same validation and transaction. It sums Rig's token
counters for the admitted offer, including responses completed before a later
failure or cancellation; a reply abandoned mid-stream has reported no usage. Managed execution requires a session; direct
demonstration emits no report. Its single, two-second write attempt survives browser disconnection but
is best effort: a write failure or process crash can lose the report without
changing the reply. A turn with no decoded model response emits no report.
Counters never enter browser events. Daily aggregation, partitioning and
retention, an outbox,
monthly closure and pseudonymization are deliberately deferred. Any future
consumption aggregate must derive from the journal.

The consumption read API exposes token totals, a continuous time series and
breakdowns by agent and model. Any authenticated person can read their own
consumption within one explicitly selected, authorized working organization.
The person must retain a live non-personal grant in that active organization;
former team/project memberships do not restrict their own historical facts within it. A direct Owner or
Analyst role on a team or project grants access to its consumption aggregates.
A team includes its projects, including retired and purged projects; a project
includes only itself. Team aggregates include project agents and their names
even when the reader has no role in those projects. This grants no content access
and exposes no per-user breakdown. Organization consumption is outside this API;
personal spaces are covered by the person's own view.

Consumption queries require an explicit period of at most 366 days. Named totals,
UTC series and agent/model breakdowns share a coherent SQL snapshot and compatible
results reuse the same aggregation. Counters travel as decimal integer strings;
rankings explicitly report truncation. Exact arithmetic over recorded reports does
not assert complete collection. An exchange counts at its first consumption,
including generated titles; it is not a count of user messages. Human-validation
resumes add tokens at their consumption time without counting that exchange again.

Consumption and its cost/impact estimates share the same read contract across
personal, team and project views. The collective screen wiring is implemented;
quality checks, tests and browser reception for that wiring remain Dimi's validation
step. Other collective indicators retain their historical read paths and access
rules. This does not establish full dashboard migration or collection completeness.
The [technical contract](A12-control-plane-api.md#consumption-analytics) identifies
its limits and verification sources.

## Operator diagnostics

The browser offers [self-tests](../../apps/frontend/README.md#weaver-self-tests) to platform administrators who also directly own at least one organization, team, or project. Operators reserve this combination of grants for pre-production testing. A run checks the platform and session once, then exercises each selected space along the organization, team and project path using the operator's rights in that space. The report groups results and skip reasons by level. Two-person isolation and an admitted turn that outlives its original user token are separate manual tests. Results stay on the page until the operator changes the path or leaves. Only identifiers needed to recover disposable fixtures survive a reload.

## Logs and lifecycle

Rust and Python processes write one line per event to stdout, in one format, and never
call a log store. k3d ships it with Fluent Bit and GKE with Cloud Logging. The chart
installs no collector, so a platform without one keeps logs in `kubectl logs` only. The
[operations reference](A3-manager-operations.md#logging) defines the format.

Lifecycle and ingestion use SQL receipts and bounded cleanup/reconciliation.
Disabling new ingestion does not discard accepted work. See the
[operations reference](A3-manager-operations.md) for logging, credentials,
retention and failure handling.
