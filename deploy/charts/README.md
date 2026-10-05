# The fred chart

`fred/` is Fred's Helm chart: fred-agents, knowledge-flow (API and workers),
control-plane (API and worker) and the frontend. Every deployment starts from it and adds
its own values file. `fred/values.yaml` holds the defaults and documents each setting.

## Requirements

- A Kubernetes cluster and [Helm](https://helm.sh/docs/intro/install/) 3 or 4.
- The services Fred uses, reached by name from the cluster: PostgreSQL, OpenSearch,
  Keycloak (a realm with the `app`, `agentic`, `knowledge-flow` and `control-plane`
  clients, plus `fred-delegation` when delegation is on), OpenFGA, Temporal, and
  S3-compatible storage or Google Cloud Storage.

## Images

The chart runs four images, `ghcr.io/thalesgroup/fred-agent/<app>`: `fred-agents`,
`knowledge-flow-backend`, `control-plane-backend` and `frontend`. The tag defaults to the
chart's `appVersion`; set `applications.<app>.image.tag` to run another one.
`make docker-build` at the repository root builds all four from this checkout.

On a local cluster, the image must be inside the cluster's nodes. For a k3d cluster, don't
import them by hand: fred-deployment-factory's `make k3d-app` builds them, copies them into
every node and deploys this chart through Helmfile (root `README.md` → "k3d Local Deployment").
The factory owns `helmfile.yaml.gotmpl` and installation values. This checkout owns
`deploy/k3d/build-images.py` (the four images and worker mapping) and
`deploy/k3d/configure.sh` (model key, dashboards and first-login guidance).
Generated `.cache/k3d/images.json` is ordinary Helm values, not a deployment blueprint.
From the factory, `make k3d-app-validate FRED_DIR=/path/to/fred` checks the chart and
installation values without building or changing the cluster. Set `FRED_IMAGE_VALUES`
to the generated file to include a prepared build in this validation.
This workflow currently targets local k3d only, using the checkout's chart.

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
  own contract: `deploy/README.md` → "Root bootstrap secret contract (AUTHZ-07)".

A complete, working example is fred-deployment-factory's `k3d-apps/fred/values.yaml`: every
address, credential and choice a deployment has to make, each one commented. The security
profile (`c3`) is described in `deploy/README.md` → "Security profiles & classification
tiers". To brand the frontend without rebuilding it, see "Theme overlay" in
`apps/frontend/README.md`.

With `storage.*_store.type: opensearch` in `fred-agents` or `knowledge-flow-backend`, the
application creates its indexes at startup.

## Deploy

```bash
helm upgrade --install fred deploy/charts/fred -n <namespace> --create-namespace \
  -f my-values.yaml --wait
```

## First login

Fred never creates Keycloak accounts. Register in the realm, then make that account the
platform's `platform_admin` with the root bootstrap (`deploy/README.md` → "Root bootstrap
secret contract (AUTHZ-07)"); `apps/control-plane-backend`'s `make bootstrap-local` does it
against any reachable control-plane.

## Kubernetes tools in fred-agents

fred-agents can inspect the cluster it runs in. It reads a kubeconfig from
`global.kubeconfig`; its server must be reachable from the pod, e.g.
`https://kubernetes.default.svc` for the cluster hosting Fred.
