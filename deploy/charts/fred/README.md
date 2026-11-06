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
| `control-plane-worker` | manager lifecycle work | yes |
| `fred-agents` | agent pod API and conversations | no |
| `fred-agents-worker` | durable preparation of the pod's installed capabilities | no |
| `monitor` | read-only namespaced technical status for platform administrators | no |
| `frontend` | web UI, behind your ingress | yes |
| `knowledge-flow-backend` | authorized search and published-content API | yes |
| `knowledge-flow-worker` | ingestion worker serving all roles | yes |
| `knowledge-flow-worker-extraction-{fast,medium,rich}` | optional dedicated extraction workers | no |

Python applications can run database migrations as Helm hook Jobs
(`applications.<name>.migration.enabled`). Control Plane reuses these hook settings
for a `schema-init` Job running `control-plane initialize-schema` with only
`DATABASE_URL`. It creates the complete Weaver schema on a fresh database, does
nothing on a matching schema and refuses an incompatible one. API startup only
verifies the schema; it never changes it.

## Requirements

- A Kubernetes cluster and [Helm](https://helm.sh/docs/intro/install/) 3 or 4.
- The services Fred uses, reached by name from the cluster: PostgreSQL, OpenSearch,
  Keycloak (a realm with `app`, `control-plane` and Knowledge Flow clients,
  plus clients required by any explicitly enabled legacy applications), Temporal, and
  S3-compatible storage or Google Cloud Storage.

## Install

```bash
helm install fred oci://ghcr.io/thalesgroup/fred-helm/fred --version <version> \
  -n fred --create-namespace -f my-values.yaml --wait
```

`helm show values oci://ghcr.io/thalesgroup/fred-helm/fred --version <version>` prints the
documented defaults. Each release's operator guide (configuration changes, migrations) is
attached to its [GitHub release](https://github.com/ThalesGroup/fred/releases).

## Images

Knowledge Flow uses two independent images under `ghcr.io/thalesgroup/fred-agent/`:
`knowledge-flow-backend` for the API and `knowledge-flow-worker` for ingestion.
`knowledge-flow-worker-pymupdf` is the optional worker variant. The extraction
worker groups inherit the common worker's image and configuration at render time.
The API has its own configuration schema and retains its service name and routes.

`deploy/k3d/build` builds both applications independently, alongside Control Plane,
Agent Pod, frontend and monitor. The split still requires developer image and
end-to-end validation; sizes and startup memory have not been measured.

## Your values file

Write one values file for your deployment and pass it with `-f`. Two things to know:

- **Match the corpus contract.** API query embeddings and index/collection must match
  worker indexing. API `published_artifacts` must read the worker publication bucket.
  Set processing and scheduler overrides only on the worker; extraction groups inherit them.
- **Manager configuration is shared.** Set configuration and `lifecycle_policy_catalog`
  on `applications.control-plane-backend`: both manager processes mount these same ConfigMaps
  and restart when either changes. Worker credentials remain separate.
- **Credentials by reference.** Point each application's `extraEnvVars` at a Secret that
  exists before the release (`valueFrom.secretKeyRef`), and give each migration Job its
  database password through `migration.extraEnvVars`. The applications read these
  variables before the `.env` file that `dotenv` renders. The root bootstrap token has its
  own contract: [Root bootstrap secret contract](https://github.com/ThalesGroup/fred/blob/swift/deploy/README.md#root-bootstrap-secret-contract-authz-07).
- **Gateway DNS.** The frontend's manager/control-plane upstream defaults use
  `control-plane-backend.<release namespace>.svc.cluster.local:8222`, even when
  instance values replace `frontend.env`. Override `FRONTEND_CONTROL_PLANE_UPSTREAM` in `env` or `extraEnvVars` for another
  address or DNS domain. Nginx's request-time resolver needs fully qualified names.

The local k3d example in fred-deployment-factory applies
[`k3d-apps/fred/values.yaml`](https://github.com/fred-agent/fred-deployment-factory/blob/swift/k3d-apps/fred/values.yaml)
followed by built image tags and operator overrides. No manager-specific factory
overlay or branch is required. The existing control-plane identity and Secret keys
are reused; database `fred` and lifecycle queue/prefix
`control-plane-lifecycle` remain unchanged. Common `scheduler.temporal.host` and
`namespace` settings on the API feed its shared lifecycle connection.
The security profile (`c3`) is described in
[Security profiles & classification tiers](https://github.com/ThalesGroup/fred/blob/swift/deploy/README.md#security-profiles--classification-tiers).
To brand the frontend without rebuilding it, see
[Theme overlay](https://github.com/ThalesGroup/fred/blob/swift/apps/frontend/README.md#theme-overlay-branding-assets-without-a-rebuild).

## Capability preparation worker

Enable `applications.fred-agents-worker.enabled` alongside `fred-agents`. The worker
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

fred-agents can inspect the cluster it runs in. It reads a kubeconfig from
`global.kubeconfig`; its server must be reachable from the pod, e.g.
`https://kubernetes.default.svc` for the cluster hosting Fred.

## Local deployment

[fred-deployment-factory](https://github.com/fred-agent/fred-deployment-factory) installs
this chart on a local k3d cluster: `make k3d-app FRED=swift APP=fred` the published Swift
release; `make k3d-app FRED=swift|weaver APP=fred DIR=<fred checkout>` to build the three images from source (`deploy/k3d/build`)
and deploy the checkout's chart with the same values.

## Pods built on Fred's libraries

An agent pod (`fred-runtime`) or a Knowledge Base pod (`fred-sdk`) that lives in its own
repository deploys from one of two generic charts, published with this one, with its image
and its configuration only:

- [`agent-pod`](https://github.com/ThalesGroup/fred/tree/swift/deploy/charts/agent-pod) —
  the pod behind a Service, and the `runtime_catalog_sources` entry that registers it,
  printed at install;
- [`knowledge-base`](https://github.com/ThalesGroup/fred/tree/swift/deploy/charts/knowledge-base)
  — the `run` worker and the `publish` Job that declares it to Fred.

Each validates the pod's configuration against the library's own model at `helm install`,
and its README (`helm show readme oci://ghcr.io/thalesgroup/fred-helm/<chart>`) lists what
a deployment must set. A pod's repository keeps only its image and its values.

## Technical monitor

Enable `applications.monitor.enabled` after making a monitor image available and
provisioning the dedicated `monitor-database` Secret with its read-only
`DATABASE_URL`. See the [monitor setup](../../../apps/monitor/README.md#enable-in-the-fred-chart)
for image values, authentication and collection limits. The chart restricts its
Kubernetes Role to namespaced list operations and routes the frontend directly to
the monitor. It creates no database, database role or persistent volume.
