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
| `fred-agents` | agent runtime: executes conversations and agents | yes |
| `frontend` | web UI, behind your ingress | yes |
| `knowledge-flow-backend` | document ingestion, search and storage API | yes |
| `knowledge-flow-worker`, `knowledge-flow-worker-extraction-{fast,medium,rich}` | ingestion workers, one per queue | no |
| `control-plane-backend` | teams, sessions, administration API | yes |
| `control-plane-worker` | control-plane background work | no |

Each application can also run its database migration as a Helm hook Job
(`applications.<name>.migration.enabled`).

## Requirements

- A Kubernetes cluster and [Helm](https://helm.sh/docs/intro/install/) 3 or 4.
- The services Fred uses, reached by name from the cluster: PostgreSQL, OpenSearch,
  Keycloak (a realm with the `app`, `agentic`, `knowledge-flow` and `control-plane`
  clients, plus `fred-delegation` when delegation is on), OpenFGA, Temporal, and
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

The chart runs four images, `ghcr.io/thalesgroup/fred-agent/<app>`: `fred-agents`,
`knowledge-flow-backend`, `control-plane-backend` and `frontend`; the workers run their
backend's image. The tag defaults to the chart's `appVersion`; set
`applications.<app>.image.tag` to run another one. `make docker-build` at the root of the
repository builds all four from source.

## Your values file

Write one values file for your deployment and pass it with `-f`. Two things to know:

- **Anchors do not carry overrides.** `values.yaml` shares blocks between an API and its
  worker through YAML anchors, which Helm resolves when it reads the file. A setting shared
  by `knowledge-flow-backend` and `knowledge-flow-worker` (or `control-plane-backend` and
  `control-plane-worker`) must therefore be repeated for both in your file.
- **Credentials by reference.** Point each application's `extraEnvVars` at a Secret that
  exists before the release (`valueFrom.secretKeyRef`), and give each migration Job its
  database password through `migration.extraEnvVars`. The applications read these
  variables before the `.env` file that `dotenv` renders. The root bootstrap token has its
  own contract: [Root bootstrap secret contract](https://github.com/ThalesGroup/fred/blob/swift/deploy/README.md#root-bootstrap-secret-contract-authz-07).

A complete, working example is the values of the local k3d instance,
[`k3d-apps/fred/values.yaml`](https://github.com/fred-agent/fred-deployment-factory/blob/swift/k3d-apps/fred/values.yaml)
in fred-deployment-factory: every address, credential and choice a deployment has to make,
each one commented. The security profile (`c3`) is described in
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

Fred never creates Keycloak accounts. Register in the realm, then make that account the
platform's `platform_admin` with the root bootstrap ([Root bootstrap secret contract](https://github.com/ThalesGroup/fred/blob/swift/deploy/README.md#root-bootstrap-secret-contract-authz-07));
`apps/control-plane-backend`'s `make bootstrap-local` does it against any reachable
control-plane.

## Kubernetes tools in fred-agents

fred-agents can inspect the cluster it runs in. It reads a kubeconfig from
`global.kubeconfig`; its server must be reachable from the pod, e.g.
`https://kubernetes.default.svc` for the cluster hosting Fred.

## Local deployment

[fred-deployment-factory](https://github.com/fred-agent/fred-deployment-factory) installs
this chart on a local k3d cluster: `make k3d-app APP=fred` the published release,
`DIR=<fred checkout>` added to build the four images from source (`deploy/k3d/build`)
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
