# monitor

Small independent Rust service using `libs/fred-rust-sdk` for authentication and
platform-role checks. A namespaced Kubernetes client reads workload readiness,
container restarts and recent events. Fred exposes the page at `/admin/monitor`
in the platform administration sidebar. No persistent incident history is stored.

| Route | Access | Meaning |
| --- | --- | --- |
| `GET /healthz` | Public | The HTTP process is alive; no platform details. |
| `GET /monitor/v1/status` | Valid human JWT and current SQL `platform_admin` grant | Returns a bounded technical snapshot of the configured namespace. |

The protected route checks the database grant on every request. Missing/invalid
JWTs return 401, service identities or missing grants return 403, and an unavailable
authorization database returns 503 without protected data. There is no anonymous
mode or cached authorization fallback. The process can start with PostgreSQL
unavailable; `/healthz` remains independent of it.

## Run locally

Set these environment variables before `make run` (or `cargo run --locked -p monitor`
from the repository root):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL for the existing Control Plane database, using a dedicated read-only account. |
| `OIDC_ISSUER` | Same trusted issuer as Fred; must match the token's `iss`. |
| `OIDC_CLIENT_ID` | Same human login client as Fred. |
| `OIDC_AUDIENCE` | Audience actually issued for and accepted by Fred's user API. |
| `OIDC_PROVIDER` | `keycloak` (default) or `oidc` for discovery. |
| `OIDC_JWKS_URL` | Optional reachable signing-key URL, without changing the trusted issuer. |
| `MONITOR_NAMESPACE` | Namespace to inspect; defaults to the Kubernetes client namespace. Helm sets the pod namespace. |
| `MONITOR_BIND` | `127.0.0.1:8223` by default; the container uses `0.0.0.0:8223`. |

The service uses the default subject/claim mapping, zero clock skew and a
maximum token lifetime of one hour, matching the Control Plane defaults. Configure
the issuer, login client and audience consistently with the actual installation.
It accepts no runtime delegation. OIDC discovery/JWKS access is needed according
to the shared verifier's provider and cache rules.

The database account needs only CONNECT, schema USAGE and SELECT on
`platform_role_grant`. Provision it externally; the monitor performs no writes or
migrations. Its pool is capped at two connections; acquisition and the complete
permission check have two-second timeouts. Do not use Control Plane owner credentials.

## Build and check

```sh
make code-quality
make test
make docker-build IMAGE_FULL=monitor:dev
```

The image builds from the repository root, runs as a non-root user and is not
published by the image release workflow. `make run` requires exported variables;
it does not load a `.env` file. No running Fred deployment is modified by these
commands except when you explicitly run the resulting application yourself.

## Kubernetes snapshot

The client uses its in-cluster service account, or the current kubeconfig locally.
No Kubernetes API connection is needed for `/healthz`; startup does require valid
client configuration. Each protected status request reads Deployments, StatefulSets,
DaemonSets, Pods and `events.k8s.io/v1` Events concurrently. It needs only `list`
on those resources in one namespace, with no cluster-wide access, logs or Secrets.

“Services” are those controllers and their ready/desired replica counts, not
Kubernetes Service endpoints or application-level HTTP health. Missing controller
observations are unknown; unavailable sources are explicit, never healthy empty
results. A source has a five-second deadline and a maximum of four 500-item pages;
truncation is visible. Up to 100 recent events from the last hour are shown, with
messages bounded to 2,048 characters. Kubernetes event retention remains authoritative.
Restart counts belong to the current pod and reset when that pod is replaced.
The last terminated state preserves evidence such as `OOMKilled` after recovery.
Completed successful job pods are omitted; pending pods remain visible.

The UI refreshes every 15 seconds and on window focus. It uses the generated
OpenAPI client and Fred's shared tables and badges. The navigation and page require
the platform-admin authority; the monitor independently verifies JWT and SQL grant
on every API call. It never calls Control Plane. The surrounding Fred UI still
uses Control Plane for its existing bootstrap and navigation authority.

## Enable in the Fred chart

Build and make the monitor image available to the cluster, then provide a Secret
named `monitor-database` in the Fred namespace, containing `DATABASE_URL` for the
read-only database account described above. The chart deliberately does not create
this credential or reuse the database owner. Override the secret reference under
`applications.monitor.env` if your deployment uses another Secret.

Use deployment values matching your built image, for example:

```yaml
applications:
  monitor:
    enabled: true
    image:
      repository: monitor
      tag: dev
```

The chart supplies its namespaced Role, ServiceAccount, Service and Deployment.
Issuer, client, audience and optional JWKS URL are inherited from the Control Plane
user security configuration; explicit monitor environment values take precedence.
The frontend routes `/monitor/` directly to this service, independently of Control
Plane. Rebuild/redeploy the frontend image as well to include the page and proxy.
Local Vite development uses `VITE_BACKEND_URL_MONITOR` (default
`http://localhost:8223`); production nginx uses `FRONTEND_MONITOR_UPSTREAM`.

Generate the TypeScript client with `make -C apps/frontend update-monitor-api`.
The generator runs without live database, identity provider or Kubernetes services.
Offline collector, access-boundary, UI and Helm rendering tests cover this increment;
no live k3d deployment or browser session is implied by those checks.
