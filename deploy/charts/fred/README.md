# fred

[Fred](https://site.fredlab.dev) is an open-source platform for putting a team to work with
AI agents on its own documents, with the identity, access control, audit and evaluation that
regulated work requires. This chart deploys the Fred platform; every deployment starts from
it and adds its own values file. Its `values.yaml` holds the defaults and documents each
setting.

- Documentation: <https://site.fredlab.dev>
- Source code: <https://github.com/ThalesGroup/fred>

## What it deploys

| Application | Role | Enabled by default |
| --- | --- | --- |
| `control-plane-backend` | admission, governance, spaces, folders and authorization API | yes |
| `fred-agents` | agent pod API and conversations | yes |
| `fred-agents-worker` | durable preparation of the pod's installed capabilities | yes |
| `monitor` | read-only namespaced technical status for platform administrators | yes |
| `frontend` | web UI, behind your ingress | yes |
| `knowledge-flow-backend` | authorized search and published-content API | yes |
| `knowledge-flow-worker` | ingestion worker serving all roles | yes |
| `knowledge-flow-worker-extraction-{fast,medium,rich}` | optional dedicated extraction workers | no |

Control Plane runs HTTP, processing coordination and lifecycle work in one process.
There is no separate Control Plane worker. The chart wires the supplied Agent Pod,
its preparation worker and the document API/worker together. Disable optional
components explicitly; disabling Fred Agents also requires disabling its worker
and replacing/removing its runtime catalogue entry and preparation binding.

Fresh installs run two pre-install hooks: Control Plane's `initialize-schema`
(weight -10), then runtime/capability migrations (weight 0). These hooks read only
external database credentials and do not depend on release-created ConfigMaps or
Secrets. API startup verifies the SQL schema. No upgrade from Swift or an older
Weaver database is supported.

## Requirements

- A Kubernetes cluster and [Helm](https://helm.sh/docs/intro/install/) 3 or 4.
- External PostgreSQL with pgvector, OpenSearch, Keycloak, Temporal and S3-compatible
  storage (or the supported runtime GCS override). Fred does not install these services.
- A fresh database with the component roles/schemas from [bootstrap.sql](files/bootstrap.sql).
  Provision these externally, or explicitly enable `postgresBootstrap.enabled` and
  supply its administrator Secret; this hook runs first (weight -20). Database creation
  remains external. Keep the dedicated `fred_monitor` reader, never the Control Plane owner.
- A trusted realm with the human `app` client and workload clients `control-plane`,
  `agentic`, `knowledge-flow` and `knowledge-flow-worker`, including the required
  audiences and delegation grants. Supply the real issuer consistently to each
  application's security and to Control Plane's preparation/processing bindings.
- The document bucket, a private runtime bucket, Temporal namespace, trusted CAs and
  credentials provisioned before installation.

## Install

```bash
helm install fred oci://ghcr.io/thalesgroup/fred-helm/fred --version <version> \
  -n fred --create-namespace -f my-values.yaml --wait
```

`helm show values oci://ghcr.io/thalesgroup/fred-helm/fred --version <version>` prints the
documented defaults. Each release's operator guide (configuration changes, migrations) is
attached to its [GitHub release](https://github.com/ThalesGroup/fred/releases).

## Images

The chart version selects matching image tags through `Chart.appVersion`; the release
workflow sets it to `v<version>`. Seven images are published under
`ghcr.io/thalesgroup/fred-agent/`: Control Plane, frontend, Fred Agents, Knowledge Flow
API, Knowledge Flow worker, its optional PyMuPDF variant, and monitor. Preparation
uses the Fred Agents image; extraction groups inherit the common ingestion image.

Use a published prerelease such as `5.0.0-alpha.1` only after its paired code/chart
release has completed. A merge on `weaver` publishes `v5-dev` images but no chart
and does not redeploy a platform. For a deliberate development deployment, override
`applications.<name>.image.tag` for every enabled base application, including monitor;
workers and hooks inherit those choices. With mutable tags, use `pullPolicy: Always`
and explicitly roll the deployments. Use exact release versions for reproducible tests.

## Your values file

Write one values file for your deployment and pass it with `-f`. Two things to know:

- **Match the corpus contract.** API query embeddings and index/collection must match
  worker indexing. API `published_artifacts` must read the worker publication bucket.
  Set processing and scheduler overrides only on the worker; extraction groups inherit them.
- **Platform values only.** Override ingress/domain/TLS, service addresses, database and
  bucket names, Secret references, model sources/credential bindings and sizing. The
  chart supplies service routes, worker commands, SQL hooks and runtime registration.
  `https://s3.example.test`, `https://identity.example.test/realms/app` and
  `your.host` are placeholders to replace.
- **Processing transport.** The worker calls `https://your.host/control-plane/v1`
  through the TLS ingress (or your TLS-enabled internal gateway). The plain HTTP
  Control Plane Service is not a TLS endpoint. Both processing sides reject HTTP
  by default. Only a local profile should supply HTTP URLs together with
  `manager_processing.allow_insecure: true` on Knowledge Flow and
  `scheduler.processing.derived.allow_insecure: true` on Control Plane; local HTTP
  original storage also needs `storage.content.allow_insecure: true`. Keep the
  worker issuer equal to the real realm used by the platform identities.
- **Independent configuration.** YAML anchors do not propagate later overrides. Keep
  Control Plane processing and Knowledge Flow worker Temporal connections/queues aligned,
  and the preparation worker connection aligned with Control Plane lifecycle. The
  preparation worker inherits Fred Agents settings at render time.
- **Credentials by reference.** Point each application's `extraEnvVars` at a Secret that
  exists before the release (`valueFrom.secretKeyRef`), and give each migration Job its
  database password through `postgresSecrets` (or `migration.extraEnvVars` to override).
  Helm replaces lists: retain all required entries when overriding `extraEnvVars`.
  The applications read these
  variables before the `.env` file that `dotenv` renders. The root bootstrap token has its
  own contract: [Root bootstrap secret contract](https://github.com/ThalesGroup/fred/blob/weaver/deploy/README.md#root-bootstrap-secret-contract-authz-07).
- **Gateway DNS.** The frontend's control-plane and knowledge upstream defaults use
  `control-plane-backend.<release namespace>.svc.cluster.local:8222` and
  `knowledge-flow-backend.<release namespace>.svc.cluster.local:8000`, even when
  instance values replace `frontend.env`. Override `FRONTEND_CONTROL_PLANE_UPSTREAM`
  or `FRONTEND_KNOWLEDGE_FLOW_UPSTREAM` in `env` or `extraEnvVars` for another
  address or DNS domain. Nginx's request-time resolver needs fully qualified names.

For an internal HTTPS object store with a private CA, create a Secret containing
`ca-bundle.pem` and mount it in the Knowledge Flow API pod. Set the DuckDB options
in the same deployment values file:

```yaml
applications:
  knowledge-flow-backend:
    configuration:
      storage:
        tabular_store:
          query:
            duckdb_ca_cert_file: /etc/fred/tls/ca-bundle.pem
            duckdb_enable_server_cert_verification: true
    extraVolumes:
      - name: duckdb-ca
        secret:
          secretName: fred-ca-bundle
    extraVolumeMounts:
      - name: duckdb-ca
        mountPath: /etc/fred/tls/ca-bundle.pem
        subPath: ca-bundle.pem
        readOnly: true
```

The CA Secret must exist before deploying the chart. If a Knowledge Flow worker
also reads tabular Parquet artifacts, repeat the configuration and mount under
`applications.knowledge-flow-worker` because YAML anchors do not carry overrides.

The local example is
[`values-weaver.yaml`](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/k3d-apps/fred/values-weaver.yaml).
Its localhost URLs, local CA mounts, demo organizations and local credentials are
instance choices, not a production profile. Consumers use the published OCI chart
with their own values; no copied templates or source build is needed.

### External Secret contract

Override existing references when your Secret names differ. No literal credentials
are required in values. The chart does not create these external Secrets.

| Secret | Required keys / use |
| --- | --- |
| `fred-secrets` | `POSTGRES_CP_PASSWORD`, `POSTGRES_KF_PASSWORD`, `POSTGRES_RUNTIME_PASSWORD`; `POSTGRES_MONITOR_DATABASE_URL` for the dedicated reader; workload keys `KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET`, `KEYCLOAK_AGENTIC_CLIENT_SECRET`, `KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET`, `KEYCLOAK_MANAGER_WORKER_CLIENT_SECRET` |
| `fred-ingestion` | `manager-s3-secret`, `processor-s3-secret`, `kf-api-s3-secret`, `agents-s3-secret`; `agents-opensearch-password`, `kf-api-opensearch-password`, `opensearch-password` |
| Operator-chosen model Secret | Keys referenced by the configured model sources and runtime/Knowledge Flow credential bindings; no provider is selected by default |
| Administrator Secret (bootstrap opt-in only) | `postgresBootstrap.adminSecretName/adminPasswordKey`; also `postgresSecrets.monitorKey` (`POSTGRES_MONITOR_PASSWORD`) in `fred-secrets` for role provisioning |

The document principals default to `fred-document-manager`, `fred-document-processor`
and `fred-document-reader`; the runtime object-store principal defaults to `fred-agents`.
Provision their bucket permissions and override the existing access-key values when
needed. The optional shared `MODEL_CATALOG_ENCRYPTION_KEY` also belongs in `fred-secrets`.
Supply `FRED_BOOTSTRAP_TOKEN` explicitly on Control Plane with a `secretKeyRef` before
first login; it is deliberately not injected by default and is never passed to hooks.

## Capability preparation worker

`fred-agents` and `fred-agents-worker` are enabled together by default. The worker
inherits the API's final image (including build overlays), runtime ID, SQL and
object storage, CP URL, workload configuration and Secret references through `inheritFrom`. Set
those on `fred-agents` only: the worker schema rejects separate image, configuration
or credential overrides, except for enabling its scheduler. The API's scheduler
setting is preserved. No second image build or capability migration is needed.

Bind the runtime ID in the CP's `platform.capability_preparation.workers` to the
verified issuer, audience and client ID of its workload. The worker and
`scheduler.lifecycle.temporal` on the CP must use the same host and namespace;
the chart rejects missing bindings or mismatched connections. The CP supplies the
actual queue; the inherited `scheduler.temporal.task_queue` does not select it.
See the [operator note](../../release-notes/changes/weaver-powerpoint-file-ownership.md)
for the retention, identity and migration contracts.

The separate Deployment runs `python -m fred_agents --mode worker`, without ports,
Service, ingress, metrics endpoint or API probes. It shares the API's `.env` Secret
and creates only its configuration, service account (without Kubernetes permissions)
and Deployment. Startup errors terminate the process; Kubernetes restarts it.
Container readiness alone does not prove Temporal polling: verify the poller and
one preparation before declaring the worker operational.

Each replica runs at most two preparation activities. Defaults bound it to 2 CPUs,
2 GiB RAM and 2 GiB ephemeral storage; these are initial limits, not measured
capacity. `terminationGracePeriodSeconds: 60` leaves time for the runtime's
30-second graceful shutdown. Replica count and resources remain configurable;
`replicaCount: 0` deliberately pauses processing while leaving the API available.
Retain workers for cleanup when disabling new preparation admissions.

## Horizontal Pod Autoscaling

Applications can opt into an `autoscaling/v2` HorizontalPodAutoscaler under
`applications.<name>.autoscaling`. Set `enabled: true`, `minReplicas`, `maxReplicas`,
and a Kubernetes resource `metrics` list. Optional `behavior.scaleUp` and
`behavior.scaleDown` values use the Kubernetes HPA behavior fields directly. The chart
ships disabled CPU policy examples for every Deployment. The four Knowledge Flow worker
examples preserve their separate queue-specific limits; the other applications have
conservative starting values. Adjust each policy and set CPU requests for its container
before enabling it. An enabled HPA requires that application's Deployment to be enabled,
CPU requests on its container, and the cluster's Kubernetes metrics API. While an HPA is
active, the chart leaves `spec.replicas` unset so the HPA can own the Deployment's replica
count. `fred-agents` must use shared storage (`gcs` or `minio`) if its autoscaling
`maxReplicas` is greater than one.

With `storage.*_store.type: opensearch` in `fred-agents` or `knowledge-flow-backend`, the
application creates its indexes at startup.

## First login

Register in the realm, accept the active terms in Fred and enter the bootstrap
secret requested by the UI to become platform owner. The manager API reads the
secret named by `app.bootstrap_token_env_var`; k3d keeps the existing
`fred-secrets/CONTROL_PLANE_BOOTSTRAP_TOKEN` key. Registration/bootstrap does not
create organization membership. See the [manager guide](../../../apps/control-plane/README.md).

## Kubernetes tools in fred-agents

The default runtime has no Kubernetes API token, Role or kubeconfig mount.
If a deployment explicitly needs Kubernetes tools, supply its scoped credentials,
mounts and RBAC in that deployment's values. Monitor has its own read-only Role.

## Local deployment

[fred-deployment-factory](https://github.com/fred-agent/fred-deployment-factory) installs
this chart on a local k3d cluster: `make k3d-app FRED=swift APP=fred` the published Swift
release; `make k3d-app FRED=swift|weaver APP=fred DIR=<fred checkout>` to build the images from source (`deploy/k3d/build`)
and deploy the checkout's chart with the same values.

## Pods built on Fred's libraries

An agent pod (`fred-runtime`) or a Knowledge Base pod (`fred-sdk`) that lives in its own
repository deploys from one of two generic charts, published with this one, with its image
and its configuration only:

- [`agent-pod`](https://github.com/ThalesGroup/fred/tree/weaver/deploy/charts/agent-pod) —
  the pod behind a Service, and the `runtime_catalog_sources` entry that registers it,
  printed at install;
- [`knowledge-base`](../knowledge-base/README.md)
  — the `run` worker and the `publish` Job that declares it to Fred.

Each validates the pod's configuration against the library's own model at `helm install`,
and its README (`helm show readme oci://ghcr.io/thalesgroup/fred-helm/<chart>`) lists what
a deployment must set. A pod's repository keeps only its image and its values.

## Technical monitor

Monitor is enabled by default and uses the same release tag as the other workloads.
It receives `DATABASE_URL` from `postgresSecrets.name/monitorUrlKey`, normally
`fred-secrets/POSTGRES_MONITOR_DATABASE_URL`. The URL must use the dedicated
`fred_monitor` reader with `cp_read` as its search path. Provisioning and grants are
owned by the existing bootstrap and Control Plane migration chain; monitor runs no
migration. Its Kubernetes Role only lists workload status/events in the release
namespace, and its API requires a current platform-admin grant.

See [monitor setup](../../../apps/monitor/README.md#enable-in-the-fred-chart) for the
OIDC and database contract. Set `applications.monitor.enabled: false` only when you
intentionally omit technical monitoring from that installation.

## Hosted applications

Organization Owners register dedicated UI/API deployments in **Administration >
Features > Apps**, and dedicated KB collectors in **Features > Knowledge Bases**.
Each deployment belongs to one organization. Registration and authorization are
stored in PostgreSQL; no additional platform activation is required. Follow the
[application and KB procedure](../../../docs/architecture/08-operations.md#organization-owned-applications-and-knowledge-bases).
This chart deploys the shared Fred core; registering an extension does not install
its containers or provision its credentials and storage. Deploy those separately
for the owning organization.

The frontend forwards `/apps/*` and `/app-services/*` to its existing Control Plane
upstream without rewriting. There is no per-application Helm configuration or
frontend restart. The chart rejects retired registration maps and application
gateway environment variables; `platform.knowledge_bases` is no longer a configuration
option. Register the collector identity in the UI before its `publish` hook runs.
