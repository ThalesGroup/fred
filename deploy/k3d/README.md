# Weaver: local ingestion and Python agent catalog deployment

On `weaver`, `deploy/k3d/build` builds `apps/control-plane` as the
`control-plane-backend` image. The ingestion profile runs it as `control-plane serve`:
HTTP, durable Temporal submission and lifecycle work share one process. Knowledge
Flow runs only its worker; its HTTP API and the separate manager worker are disabled.

The k3d profile enables `scheduler.lifecycle.enabled` for deletion admission and
lifecycle processing through `temporal:7233` in the same control-plane process.
Its purge retention is one minute (`PT1M`); physical cleanup follows worker execution.

This checkout owns the complete profile in `deploy/k3d/helmfile.yaml.gotmpl`,
`values.yaml.gotmpl` and its `prepare` hook. `base-values.yaml.gotmpl` imports
the shared factory values while removing the worker's legacy MinIO storage
blocks before Helm merges the local worker configuration. `secondary-values.yaml.gotmpl`
renders the factory's secondary URLs. Both drop any factory control-plane
configuration: the control-plane gets the chart defaults plus the k3d addresses in
`values.yaml.gotmpl`. The factory supplies infrastructure,
URLs, its shared base values and the generic build/import/sync sequence. Its
`APP=fred DIR=...` command selects the checkout's Helmfile when present.
No Rust-specific profile is added to the factory.

## Python agent catalog on secondary

The profile enables the real `fred-agents` Python deployment and its runtime /
installed-capability migration job. `deploy/k3d/build` already builds that image
through its existing `docker-build` target and supplies its content-derived tag
through `images.txt` and `images.yaml`. The preparation hook accepts the four
application deployments, including this pod.

The Control Plane is configured with runtime ID `fred-agents` and base URL
`http://fred-agents/fred/agents/v2`. It reads the existing public
`GET /agents/templates` response, including `fred.github.assistant` and its full
tuning metadata. There is no runtime registration callback or new announcement
protocol. Service `fred-agents` maps port 80 to container port 8000; the ingress
also routes `/fred/agents/v2` to this service on the secondary host.

The pod's Weaver startup reads the Rust-published `authorization_store` binding
from PostgreSQL, validates the exact canonical model distributed in its image,
and pins OpenFGA store/model IDs with HIGHER_CONSISTENCY. It does not create or
synchronize an OpenFGA model or require the old Python Control Plane admission
tables. C3, verified identity/delegation and the configured `terms_acceptance`
contract remain required. Both services use CGU version `v1` and the configured
store identity `control-plane`.

The inherited factory settings are retained:

| Dependency | Effective profile |
| --- | --- |
| PostgreSQL / migrations | Database `fred`, user `fred`, host `postgres`; password from `fred-secrets/POSTGRES_FRED_PASSWORD`. The enabled job runs `python -m fred_runtime migrate`, including installed capabilities, without old Python Control Plane migrations. |
| OpenFGA | `http://openfga:9080`, token from `fred-secrets/OPENFGA_API_TOKEN`; Rust must have published the binding. |
| Keycloak | Secondary issuer/origins, user and M2M authentication; workload client `agentic` and secret `fred-secrets/KEYCLOAK_AGENTIC_CLIENT_SECRET`. Existing outgoing delegation is retained. |
| Storage / observability | SeaweedFS runtime object store, OpenSearch logs/KPI, Prometheus and node CA mount; their inherited credential references are retained. |
| Models | Existing mounted Mistral and mock profiles; `fred-model-credentials/OPENAI_API_KEY` remains required by preparation. Catalog discovery invokes no model. Web research stays disabled. |
| Control Plane | Pod URL `http://control-plane-backend:8222/control-plane/v1` comes from the chart. The Rust resolver is implemented, but the Python execution consumer still requires adaptation. |

After deploying, use organization administration -> Agents to find and activate
`fred.github.assistant`, then verify the list after reload. The deployment does
not enable templates in organizations, select models or alter instance settings.
Ralph and its embedded execution path are unchanged. Unavailable template
dependencies still prevent their activation. Discovery still fails globally if
an enabled catalog source cannot be reached, including while the pod is starting.

This increment prepares deployment and discovery; it does not complete the chat
journey. The Python consumer of `/spaces/.../runtime`, resource execution gates,
preparation and session/UI wiring remain subsequent work. The new Rust incoming
delegation setting is not activated in this discovery-only increment; it belongs
with the Python consumer and the corresponding generated config schema update.
The pod remains the actual runtime, with no catalog mode or temporary execution
block added. No build, render, schema generation, test or deployment was run by
the assistant; Dimi owns those checks and the cluster rollout.

## Prepare and deploy

Use the updated factory script that recognizes a checkout-owned Helmfile and
exports `K3D_FACTORY_ROOT`. Run these commands yourself from the factory checkout:

```sh
cd ~/Rebac/fred-deployment-factory
export ENV=secondary
# Infrastructure must be running; omit if already done.
make k3d-up
# Validate/render only, without building or provisioning.
make k3d-app-validate APP=fred DIR=../fred
# Build, import images, prepare the ingestion dependencies, then deploy.
make k3d-app ENV=secondary APP=fred DIR=../fred
```

`ENV` selects the cluster, not the branch or directory. This experimental profile
requires `ENV=secondary` so it cannot replace the default Swift installation.
The factory's usual `APP=fred` behavior is retained for checkouts without their
own Helmfile. The model key must already exist in the secondary cluster's
`fred-model-credentials/OPENAI_API_KEY`; the hook checks it and never copies a
key from another checkout or cluster. Host Python needs PyYAML, as do the
factory's identity helpers.

The four application deployments are `control-plane-backend`, `knowledge-flow-worker`,
`frontend` and `fred-agents`. The manager image occupies the chart's
`control-plane-backend` key and runs `control-plane serve`; the separate
control-plane worker and KF HTTP API / SQL migration remain disabled. Manager
and runtime migrations are enabled. Manager and the Python agent runtime access
PostgreSQL and the published OpenFGA model; the ingestion worker keeps its scoped
storage credentials.

The generic identity hook provisions `knowledge-flow-worker`. The checkout's
`prepare` hook then:

- exports the processing contract from the built KF image and effective config;
- creates retained application credentials in `fred-ingestion`;
- supplies SeaweedFS with an application-owned Secret containing its existing
  identities plus manager/input and worker/output policies, and waits for its
  rollout; creates `app-content-documents` if absent;
- configures the worker's OIDC audience/claims and scoped OpenSearch identity;
- creates the contract ConfigMap and a digest annotation to restart manager
  when the worker image or contract changes.

This local hook changes the SeaweedFS deployment's configuration volume in the
selected cluster. A later `make k3d-up` can restore the factory configuration;
rerun `make k3d-app APP=fred DIR=../fred` afterwards to reapply the ingestion
setup. It does not change the factory chart or reset existing data. Secrets and
the contract remain outside Helm's application release so they survive an app
uninstall. The dedicated Temporal queue is `manager-ingestion`.

Infrastructure admin credentials are used by preparation only. KF receives its
manager service identity, output-only S3 credentials and scoped OpenSearch
credentials. The frontend receives no infrastructure credentials.

This profile does not migrate existing persisted resources. Application data reset
is unsupported for the Rust ingestion profile and is refused before mutation.
Recreating a disposable secondary installation is a separate operator action.

The vector index is configured in `manager_processing.vector_store.index`.
Preparation reads that same rendered value to grant index permissions. It also
reads the configured KPI index when its OpenSearch sink is enabled. Wildcards and
invalid index names are rejected before provisioning; no index name is embedded
in the preparation script.

## Read the storage and authority model

The [canonical layout](../../docs/architecture/A9-documents.md#physical-object-layout)
preserves the Swift documents bucket, here `app-content-documents`, and its
document-local input/output roots. Immutable generation directories fence stale
processing writes. `app-content-objects` and `filesystem` keep their existing use.
SQL remains the authority for publication and placement; listing S3 is not a
document inventory or an authorization check.

| Process | Object access | Other responsibility |
| --- | --- | --- |
| Manager API | Read both zones, write/delete input, inspect bucket configuration | Upload, authorized original streaming, artifact verification/publication |
| Manager background tasks (same process) | Manager credentials | SQL outbox, Temporal delivery, reconciliation and lifecycle |
| KF worker | Read/write/delete/list output only | Existing processors and vector adapter; originals through manager |
| Frontend | No object credential | Existing Resources pages and authenticated manager calls |

Vector fields/mapping remain Swift's. Generation-scoped chunk IDs prevent stale
overwrites. `document-vectors` stays separate because legacy retrieval does not
enforce manager publication or ReBAC. File/Raw previews work through manager;
this profile does not add manager search/chat support.

The profile caps uploads at four times 100 MiB (400 MiB spool, 2 GiB pod ephemeral
limit). KF runs four roles with one activity each, 1 GiB workspace per activity
and an 8 GiB ephemeral limit. These are admission/resource bounds, not measured
production capacity. Legacy PDF expiry is disabled. Do not run legacy document
repair/deletion against manager content.

## First PDF validation

Follow the [PDF user journey](../../docs/architecture/02.2-document-journey.md):
create/open a folder as an editor, upload a text PDF with profile `fast`, observe
the stored original and processing progress, then reload, inspect File/Raw and
download the original. Compare SHA-256 before and after.

The journey includes read-only SQL, S3 and OpenSearch commands. Record the
document/processing/generation IDs, exact object keys and published chunk IDs.
Retry uses the stored original. KF HTTP ingestion is not part of this path.
Inspect safe logs and Temporal history for a failure before retrying; never
publish a JWT, Secret or provider request body as test evidence.

## Local versus production

This fixture exercises the S3 API on SeaweedFS 4.29 with explicit IAM policies,
separate application Secrets and scoped OpenSearch rights. HTTP, self-signed
OpenSearch TLS, static Secrets and single replicas are local choices. Production
GCS/S3NS identity/API mode and effective path/list permissions require operator
evidence; native GCS/Workload Identity support is not established by this fixture.
No bucket rename or data migration runs with these commands.

Read [operations](../../docs/architecture/A3-manager-operations.md#complete-local-ingestion-profile)
and [costs/limits](../../docs/architecture/09-quality.md#original-storage-costs-and-failure-evidence)
for shared-bucket scan cost, cleanup retry behavior and the callback timeout boundary.
