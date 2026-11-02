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
`document-vectors`, separately from Swift's retrieval index.

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

## Logs and lifecycle

Lifecycle and ingestion use SQL receipts and bounded cleanup/reconciliation.
Disabling new ingestion does not discard accepted work. See the
[operations reference](A3-manager-operations.md) for logging, credentials,
retention and failure handling.
