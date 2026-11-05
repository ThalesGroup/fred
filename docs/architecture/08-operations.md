# 8. Operations

## Deployment and configuration

The checkout-owned [k3d profile](../../deploy/k3d/README.md) deploys
`control-plane-backend`, `knowledge-flow-worker` and `frontend` in the secondary
cluster. The deployment factory supplies infrastructure and the generic application
build/import/sync sequence. The control-plane configuration comes only from the chart
defaults and this profile, which declares the k3d service addresses; any factory
configuration for it is discarded. The frontend forwards `/control-plane/v1` to port 8222.

Rust configuration is validated against its generated schema. Credentials are
references to Secrets, never literal values in application configuration.
`control-plane serve` supervises HTTP, original-storage cleanup, the processing
outbox and lifecycle work in one process. Knowledge Flow runs its Temporal worker.
There is no separate `control-plane worker` command in this runtime.

## Ingestion preparation

The prepare hook reads the rendered worker configuration and exports the processing
contract from the built worker image. It provisions the required storage and service
identities and the OpenSearch pipeline. OpenSearch index permissions use the
configured `manager_processing.vector_store.index` and, when enabled, the configured
KPI index. Permission targets must be concrete index names; wildcards are refused
before any provisioning. The document index name is independent of the backend name.

The hook does not infer resources from a component-name prefix. The worker uses the
same rendered configuration as the permission setup. The local profile selects
`document-vectors`, `weaver-app-logs` and `weaver-kpi`: Swift can share the
OpenSearch instance, never these indexes.

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
secondary installation is a separate, explicit operator action.

## Consumption, observation and technical health

Each figure has one authoritative source. The registry in Control Plane's
PostgreSQL records exactly and idempotently how much was consumed or owned,
by whom and for which resource. Tokens belong to this registry. If a figure will
ever be compared with a limit, a bill or a quota, it belongs in the registry.
OpenSearch serves agent-behavior observation, where occasional loss is acceptable.
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
consumption across all spaces, even after losing their roles. A direct Owner or
Analyst role on a team or project grants access to its consumption aggregates.
A team includes its projects, including retired and purged projects; a project
includes only itself. Team aggregates include project agents and their names
even when the reader has no role in those projects. This grants no content access
and exposes no per-user breakdown. Organization consumption is outside this API;
personal spaces are covered by the person's own view.

The default range is the last 30 days, with a maximum of 366 days. Buckets use UTC:
hourly up to 48 hours, daily up to 92 days, then weekly, with zeros for empty
buckets. User-timezone bucketing is deferred. A turn counts once at its first
consumption; resuming after human validation adds tokens at their consumption
time without another turn, even across days or query boundaries.

## Logs and lifecycle

Lifecycle and ingestion use SQL receipts and bounded cleanup/reconciliation.
Disabling new ingestion does not discard accepted work. See the
[operations reference](A3-manager-operations.md) for logging, credentials,
retention and failure handling.
