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
| `fred-agents` | legacy agent runtime | no |
| `frontend` | web UI, behind your ingress | yes |
| `knowledge-flow-backend` | document ingestion, search and storage API | yes |
| `knowledge-flow-worker` | ingestion worker serving all roles | yes |
| `knowledge-flow-worker-extraction-{fast,medium,rich}` | optional dedicated extraction workers | no |

Python applications can run database migrations as Helm hook Jobs
(`applications.<name>.migration.enabled`). The control-plane hook runs `control-plane migrate` using only `DATABASE_URL`;
manager also applies its SQL migrations at API startup.

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

The default chart runs three images, `ghcr.io/thalesgroup/fred-agent/<app>`:
`control-plane-backend`, `knowledge-flow-backend` and `frontend`. Each API/worker pair uses
its backend's image. The tag defaults to the chart's `appVersion`; set matching
`applications.<app>.image.tag` values for each pair when overriding it.
`deploy/k3d/build` builds these three images from the same checkout. The control-plane image is built from `apps/control-plane`; the Python
control-plane image is not published by this checkout.

## Your values file

Write one values file for your deployment and pass it with `-f`. Two things to know:

- **Anchors do not carry overrides.** `values.yaml` shares blocks between an API and its
  worker through YAML anchors, which Helm resolves when it reads the file. A setting shared
  by `knowledge-flow-backend` and `knowledge-flow-worker` must therefore be repeated for both in your file.
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
this chart on a local k3d cluster: `make k3d-app APP=fred` the published release,
`DIR=<fred checkout>` added to build the three images from source (`deploy/k3d/build`)
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
