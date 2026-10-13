# agent-pod

Deploys an agent pod built on [Fred](https://github.com/ThalesGroup/fred)'s `fred-runtime`:
your image, your pod's configuration, next to an existing Fred platform. The chart is
generic; nothing in it names a particular pod.

## TL;DR

```bash
kubectl -n fred create secret generic my-agents-secrets \
  --from-literal=KEYCLOAK_MY_AGENTS_CLIENT_SECRET=... \
  --from-literal=FRED_POSTGRES_PASSWORD=... \
  --from-literal=OPENSEARCH_PASSWORD=... \
  --from-literal=OPENFGA_API_TOKEN=... \
  --from-literal=OPENAI_API_KEY=...

helm install my-agents oci://ghcr.io/thalesgroup/fred-helm/agent-pod --version <version> \
  -n fred -f my-agents.yaml
```

with `my-agents.yaml`:

```yaml
image:
  repository: registry.example.com/my-agents
  tag: v1.0.0
secret:
  existingSecret: my-agents-secrets
configuration:
  app:
    runtime_id: my-agents
    name: My agents
    base_url: /my/agents/v2
    port: 8020                     # the port the image serves on
  security:
    m2m:
      realm_url: http://keycloak:8080/realms/app
      client_id: my-agents
      secret_env_var: KEYCLOAK_MY_AGENTS_CLIENT_SECRET
    user:
      realm_url: http://keycloak:8080/realms/app
      client_id: app
```

The install prints the entry that registers the pod in Fred (see
[Register](#register-in-fred)). The chart's `appVersion` is the version of Fred's
libraries whose configuration model it validates: build the pod on that version.

## What it deploys

| Resource | Role |
| --- | --- |
| `Deployment <release>-agent-pod` | the pod, running the image's own command |
| `Service <release>-agent-pod` | ClusterIP `service.port`, to the pod's `configuration.app.port` |
| `ConfigMap <release>-agent-pod-config` | `configuration.yaml` and `extraConfigFiles`, mounted under `/app/config/` |
| `Ingress` | only with `ingress.enabled`, on `configuration.app.base_url` |
| `Secret <release>-agent-pod-secret` | only with `secret.create: true` |

## Prerequisites

What the Fred platform must provide; the addresses go in `configuration`.

- **Keycloak**, the platform's realm: users sign in through its `app` client, and the pod
  needs its own confidential client with a service account holding `app/service_agent`
  (plus `fred-delegation/delegation_caller` when `security.delegation.act_for_people` is on).
- **The Control Plane and Knowledge Flow** the pod calls (`platform.control_plane_url`,
  `ai.knowledge_flow_url`).
- **PostgreSQL**, when `storage.postgres` is set: the LangGraph checkpointer, in Fred's
  database. **OpenSearch**, when `storage.opensearch` is set. **OpenFGA**, when
  `security.rebac` is enabled (required by `security.profile: c3`).
- **A model provider** for the models the pod's catalog names.

## Configure

### Required

| Value | Meaning |
| --- | --- |
| `image.repository`, `image.tag` | The pod's image. There is no default. |
| `configuration.app.runtime_id` | The pod's identity in Fred, its logs and its metrics. |
| `configuration.app.base_url` | The path the pod serves, and its `ingress_prefix` in Fred: canonical, as the Control Plane requires (`/my/agents/v2`: leading `/`, no trailing `/`, no `//`, `.` or `..`). |
| `configuration.security.m2m`, `configuration.security.user` | The pod's own client and the users' realm (`realm_url`, `client_id`). |
| Credentials | `secret.existingSecret`, `secret.create`, or an `extraEnvVars` entry named after `configuration.security.m2m.secret_env_var`; the chart refuses to render without one while M2M is enabled. |

`configuration` is the pod's configuration file, fred-runtime's `AgentPodConfig`.
`values.schema.json` embeds that model: a misspelled or misplaced key fails at
`helm install`, with its path.

### Credentials

Environment variables, read from Secrets only:

| Variable | Read by |
| --- | --- |
| the one `configuration.security.m2m.secret_env_var` names | the pod's M2M client |
| `FRED_POSTGRES_PASSWORD` | `configuration.storage.postgres` |
| `OPENSEARCH_PASSWORD` | `configuration.storage.opensearch` |
| `OPENFGA_API_TOKEN` | `configuration.security.rebac` |
| the model keys the catalog names (e.g. `OPENAI_API_KEY`) | the models |

`secret.existingSecret` mounts a whole Secret; `extraEnvVars` reads single keys from
Secrets the platform already owns (`valueFrom.secretKeyRef`), under other key names;
`secret.create` renders `secret.data`, for tests only.

### Optional

| Value | Default | Meaning |
| --- | --- | --- |
| `extraConfigFiles` | `{}` | other files under `/app/config/` (`models_catalog.yaml`...); a file left out stays the image's |
| `configuration.observability.kpi.prometheus` | not exposed | with `enabled: true` and `address: 0.0.0.0`, the chart opens `port` (9000 by default) and annotates the pod for scraping; it refuses a loopback address, the library's default |
| `ingress` | off | browser route on `base_url`; Fred's own Ingress usually carries it already |
| `service.port` | `80` | |
| `replicaCount`, `resources` | `1`, see `values.yaml` | |
| `extraVolumes`, `extraVolumeMounts` | `[]` | e.g. a CA bundle |
| `imagePullSecrets` | `[]` | for a private registry |

## Register in Fred

Fred serves the pod's agents once the Control Plane lists it. `helm install` prints the
entry, filled in for this release (`helm get notes <release>` prints it again); add it to
`runtime_catalog_sources` in the Fred chart's values
(`applications.control-plane-backend.configuration.platform`) and restart the Control Plane.

## Upgrade and uninstall

A change to `configuration` or `extraConfigFiles` restarts the pod (checksum annotation).
`helm uninstall` removes the workloads; conversations stay in Fred's database.
