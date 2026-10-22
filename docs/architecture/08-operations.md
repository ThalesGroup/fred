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

## SQL migrations and recovery

The pre-install/pre-upgrade Job invokes `control-plane migrate`, applying the
embedded, numbered SQLx migration chain. API startup checks versions and checksums;
it never modifies the schema. Applied migrations are immutable. See the
[SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue) and
[SQLx procedure](A3-manager-operations.md#sqlx-schema-evolution).

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
