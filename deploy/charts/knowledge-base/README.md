# knowledge-base

Deploys a Knowledge Base pod built on [Fred](https://github.com/ThalesGroup/fred)'s
`fred-sdk`: your image, your pod's configuration, next to an existing Fred platform. The
chart is generic; nothing in it names a particular Knowledge Base.

## TL;DR

```bash
kubectl -n fred create secret generic my-kb-secrets \
  --from-literal=FRED_KB_CLIENT_SECRET=...

helm install my-kb oci://ghcr.io/thalesgroup/fred-helm/knowledge-base --version <version> \
  -n fred -f my-kb.yaml
```

with `my-kb.yaml`:

```yaml
image:
  repository: registry.example.com/my-kb
  tag: 1.0.0
secret:
  existingSecret: my-kb-secrets
configuration:
  app:
    runtime_id: my-kb
  knowledge_base:
    prefix: my.kb
    control_plane_url: http://control-plane-backend:8222/control-plane/v1
    knowledge_flow_url: http://knowledge-flow-backend:8000/knowledge-flow/v1
  security:
    m2m:
      realm_url: http://keycloak:8080/realms/app
      client_id: kb-my
      secret_env_var: FRED_KB_CLIENT_SECRET
  scheduler:
    temporal:
      host: temporal:7233
```

Fred lets the pod declare itself only if its client owns the prefix: add one entry,
keyed by the client, to `registrations.knowledgeBasePublishers` in the Fred chart's
values, then upgrade Fred. The install prints it:

```yaml
registrations:
  knowledgeBasePublishers:
    kb-my:
      prefix: my.kb
```

The chart's `appVersion` identifies the `fred-sdk` version used to generate its
configuration schema. Build the pod with a compatible `fred-sdk` version.

## What it deploys

| Resource | Role |
| --- | --- |
| `Deployment <release>-knowledge-base` | the worker, `run`: polls Temporal and serves runs; opens no inbound port |
| `Job <release>-knowledge-base-publish` | `publish`, a hook after each install, upgrade and rollback: declares the Knowledge Base to Fred, then exits |
| `ConfigMap <release>-knowledge-base-config` | `configuration.yaml`, mounted at `/app/config/` |
| `Service <release>-knowledge-base-metrics` | only the metrics ports enabled under `configuration.observability` |
| `ServiceMonitor` | only with `metricsService.serviceMonitor.enabled` (Prometheus Operator) |
| `Secret <release>-knowledge-base-secret` | only with `secret.create: true` |

## Prerequisites

What the Fred platform must provide; the addresses go in `configuration`.

- **Keycloak**, the platform's realm: the pod's own confidential client, with a service
  account holding `app/service_agent`.
- **The Control Plane and Knowledge Flow** (`knowledge_base.control_plane_url`,
  `knowledge_base.knowledge_flow_url`).
- **Temporal** (`scheduler.temporal`).
- Whatever source the pod reads (a share, a repository...): its settings are the pod's own,
  usually environment variables (`extraEnvVars`).

## Configure

### Required

| Value | Meaning |
| --- | --- |
| `image.repository`, `image.tag` | The pod's image. There is no default. |
| `configuration.app.runtime_id` | The pod's identity in metrics and logs; one per release. |
| `configuration.knowledge_base.prefix`, `.control_plane_url` | The Knowledge Base's name prefix in Fred, and where it declares itself. |
| `configuration.security.m2m` | The pod's own client (`realm_url`, `client_id`, `secret_env_var`). |
| Credentials | `secret.existingSecret`, `secret.create`, or an `extraEnvVars` entry named after `configuration.security.m2m.secret_env_var`; the chart refuses to render without one. |

`configuration` is the pod's configuration file, fred-sdk's Knowledge Base
`PodConfiguration`. `values.schema.json` embeds that model: a misspelled or misplaced key in
one of its sections (`app`, `knowledge_base`, `security`, `scheduler`, `observability`) fails
at `helm install`, with its path. A Knowledge Base that extends `PodConfiguration` keeps its
own top-level section in the same file (e.g. `webdav:`); the chart passes it through.

### Credentials

The client secret is the environment variable `configuration.security.m2m.secret_env_var`
names, plus whatever the pod's source needs. `secret.existingSecret` mounts a whole Secret;
`extraEnvVars` reads single keys from Secrets the platform already owns
(`valueFrom.secretKeyRef`); `secret.create` renders `secret.data`, for tests only.

### Optional

| Value | Default | Meaning |
| --- | --- | --- |
| `configuration.observability.kpi.prometheus`, `.temporal.prometheus` | not exposed | the pod's and the workflow engine's metrics: with `enabled: true` and `address: 0.0.0.0`, the chart opens `port` (9000, 9001 by default) and the metrics Service; it refuses a loopback address, the library's default |
| `metricsService.serviceMonitor.enabled` | `false` | a ServiceMonitor for the Prometheus Operator |
| `publish.enabled` | `true` | the declaration Job; turn off to declare by other means |
| `extraVolumes`, `extraVolumeMounts` | `[]` | e.g. a private CA bundle for the source |
| `resources`, `publish.resources` | see `values.yaml` | |
| `imagePullSecrets` | `[]` | for a private registry |

### Writable paths

The container's root filesystem is read-only (`securityContext.readOnlyRootFilesystem`);
only `/tmp` is writable. A pod that caches or clones under its home directory needs that
directory pointed at `/tmp` (for example `XDG_CACHE_HOME=/tmp/cache` in `extraEnvVars`) or a
volume (`extraVolumes`, `extraVolumeMounts`).

## Enable in Fred

Once the Fred chart registers the client under `registrations.knowledgeBasePublishers` and the
`publish` Job succeeds, the Knowledge Base appears in Fred's admin; a platform
admin enables it for the teams that should use it.

## Upgrade and uninstall

Each upgrade re-runs `publish`; a change to `configuration` restarts the worker.
`helm uninstall` removes the workloads; what the Knowledge Base ingested stays in Fred.
