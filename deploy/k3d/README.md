# Weaver on the local k3d instance

## Local installation

This directory only holds the image build (`build`). The deployment itself is standard
Helm and lives in [fred-deployment-factory](https://github.com/fred-agent/fred-deployment-factory):
`k3d-apps/fred/values-weaver.yaml` is this instance's plain values for this checkout's
chart, and `k3d/values.yaml` (`lines.weaver`) is what the infrastructure provisions for it.

From the factory, `make k3d-up` prepares the infrastructure, then
`make k3d-app FRED=weaver APP=fred DIR=<this checkout>` builds and deploys this checkout.
`FRED` is required and the only selector; this checkout is verified against it. The factory
never changes Git branches. `make k3d-app-validate FRED=weaver APP=fred DIR=<this checkout>`
renders without building or changing the cluster.

`FRED=weaver` gives context `k3d-fred`, namespace `fred-weaver`, database
`fred_weaver`, Temporal namespace `fred-weaver`, and <http://weaver.localhost:8088>.
Infrastructure is in namespace `fred-infra`. Swift, when deployed, has its own namespace,
database and OpenSearch indexes (Weaver: `document-vectors`, `weaver-kpi`). Login accounts and the S3 document bucket are shared; no users, grants, documents or conversations are migrated by deployment.

On `weaver`, `deploy/k3d/build` builds `apps/control-plane` as the
`control-plane-backend` image. The ingestion profile runs it as `control-plane serve`:
HTTP, durable Temporal submission and lifecycle work share one process. Knowledge
Flow runs its worker and its HTTP API, the latter as the capability backend called by
agent pods; the separate manager worker is disabled.

The k3d profile enables `scheduler.lifecycle.enabled` for deletion admission and
lifecycle processing through `temporal:7233` in the same control-plane process.
Its purge retention and lifecycle sweep interval are each one minute (`PT1M`).
After retention expires, physical cleanup starts on a subsequent sweep; it is not
guaranteed to finish exactly one minute after the UI deletion.

## Technical monitor

The profile builds `apps/monitor` and exposes `/admin/monitor` to platform admins.
The chart's `postgresBootstrap` hook runs this chart's `files/bootstrap.sql` with the
administrator password of the `postgres-admin` Secret, then sets the four role passwords of
`fred-secrets`: `POSTGRES_CP_PASSWORD`, `POSTGRES_KF_PASSWORD`,
`POSTGRES_RUNTIME_PASSWORD`, `POSTGRES_MONITOR_PASSWORD`. The factory also provides
`POSTGRES_MONITOR_DATABASE_URL`. No password is printed or passed in argv; SQLx owns all
`cp_read` grants.

The application bootstrap installs vector in Weaver's knowledge schema, inside
`fred_weaver`. Swift's separate database keeps its infrastructure initialization.
A deployment does not convert old incompatible schemas or reset data. For a
separately authorized disposable reset, use `make k3d-wipe` from the factory; this
removes the entire cluster and every application's data. Then run `make k3d-up` again
and recreate the operator-owned Secrets.

Never reset a database containing data to keep. See the
[DBA procedure](../postgres/README.md) for managed installations and role cleanup.

## First start on k3d

The path a new contributor follows, from an empty cluster to an assistant that
answers from a team's documents. Weaver runs on k3d only; the factory's Docker
Compose setup does not support it yet.

**Prerequisites.** Sibling checkouts of `fred` (branch `weaver`) and
`fred-deployment-factory`, the tools listed in the factory README, the line
`127.0.0.1 keycloak weaver.localhost` in `/etc/hosts`, and a Mistral
API key.

**1. Cluster and Fred.** From the factory checkout:

```sh
make k3d-up   # the infrastructure, and the namespace, database and identities of each line
kubectl --context k3d-fred -n fred-weaver create secret generic fred-model-credentials \
  --from-file=OPENAI_API_KEY=/absolute/path/to/mistral-key
make k3d-app FRED=weaver APP=fred DIR=/absolute/path/to/this/checkout
kubectl --context k3d-fred -n fred-weaver get deploy
```

`control-plane-backend`, `knowledge-flow-backend`, `knowledge-flow-worker`,
`fred-agents`, `fred-agents-worker` and `frontend` must be `1/1`. `make k3d-app` ends by printing the
command that reads the bootstrap token.

**2. Platform admin.** Open <http://weaver.localhost:8088>, sign in with the intended
admin identity (register only if needed), activate platform administration with the
bootstrap token, then accept the terms of use ([journey](../../docs/architecture/02.1-user-journeys.md#from-an-empty-platform-to-an-organizations-first-user)).

**3. Example people and spaces.** Build the demo bundle, then import it as the
owner in **Provisioning**:

```sh
make bundle-demo   # -> apps/control-plane/target/demo-provisioning-bundle.zip
```

It creates Acme (team Research) and Globex (team Support) with the thirteen
accounts of the [example table](../../docs/architecture/02-journeys.md#example-people-and-spaces);
each account's password is `Azerty123_`.

**4. Models and assistant template.** As `alice`, authorize
`mistral-small-latest` and `mistral-medium-latest` in **Models** and choose a
default, then activate `fred.github.assistant` in the organization's **Agents**
([journey](../../docs/architecture/02.3-agent-administration.md)).

**5. First answer from documents.** As `bob`, in Research: upload a text PDF in
**Resources** with profile `fast` and wait until it is processed
([journey](../../docs/architecture/02.2-document-journey.md)). Create a Custom
assistant with **Team documents** enabled and ask about the PDF: the answer cites
it and its sources are visible
([journey](../../docs/architecture/02.3-agent-administration.md#bobs-assistant-answers-from-researchs-documents)).

**What does not work yet.** Screens still calling the retired Python control plane
(`slices/legacyControlPlane`) fail: parts of Home, Prompts, Wiki, knowledge bases,
applications, marketplace and most platform administration pages. Among agent
capabilities, only document search is wired. [AGENTS.md](../../AGENTS.md#weaver-fred-5x-current-state-versus-target)
states the current and target state of each component.

**Day to day.** `make k3d-app-validate FRED=weaver APP=fred DIR=../fred` renders
without building. Read a component's logs with
`kubectl --context k3d-fred -n fred-weaver logs deploy/<name>`. The root
`make test` needs network access: it installs each component's dependencies and
the frontend packages' consumer caches before running offline tests.

## Python agent catalog on k3d

The profile enables the real `fred-agents` Python deployment and its runtime /
installed-capability migration job. `deploy/k3d/build` already builds that image
through its existing `docker-build` target and supplies its content-derived tag
through `images.txt` and `images.yaml`.

The Control Plane is configured with runtime ID `fred-agents` and base URL
`http://fred-agents/fred/agents/v2`. It reads the existing public
`GET /agents/templates` response, including `fred.github.assistant` and its full
tuning metadata. There is no runtime registration callback or new announcement
protocol. Service `fred-agents` maps port 80 to container port 8000; the ingress
also routes `/fred/agents/v2` to this service on the Weaver host. This same
path is declared as `public_base_url`, used by execution preparation and session
history to give the browser approved runtime URLs.

The pod validates identity and obtains the admitted turn context from Control Plane.
Control Plane evaluates permissions from PostgreSQL roles. Knowledge Flow API
requests the authorized document scope with its own M2M bearer and the verified
person/run/agent triplet. The infrastructure's Keycloak post-install grants its service
account the configured delegation caller role, which conveys no content or platform-admin rights.
C3 and the configured terms acceptance remain required.

The inherited factory settings are retained:

| Dependency | Effective profile |
| --- | --- |
| PostgreSQL / migrations | Database `fred_weaver`, host `postgres`; API and preparation worker use runtime login `fred_runtime`, schema `runtime`, password from `fred-secrets/POSTGRES_RUNTIME_PASSWORD`. The API's enabled migration job runs `python -m fred_runtime migrate`, including installed capabilities, after CP schema initialization. The worker runs no migration. |
| Keycloak | Secondary issuer/origins, user and M2M authentication; workload client `agentic` and secret `fred-secrets/KEYCLOAK_AGENTIC_CLIENT_SECRET`. Existing outgoing delegation is retained. |
| Storage / observability | SeaweedFS runtime object store, OpenSearch KPI, Prometheus and node CA mount; their inherited credential references are retained. |
| Models | The control plane discovers the Mistral source; the pod retains only its inference credential binding. Both explicitly use `fred-model-credentials/OPENAI_API_KEY`. Discovery invokes no model. Web research stays disabled. |
| Control Plane | Pod URL `http://control-plane-backend:8222/control-plane/v1` comes from the chart. The pod resolves each turn through the Rust resolver using trusted delegation. |

After deploying, use organization administration -> Agents to find and activate
`fred.github.assistant`, then verify the list after reload. The deployment does
not enable templates in organizations or alter instance settings. The explicit
organization model declarations below initialize model policy once.
Ralph runs embedded in Control Plane. Its document search calls Knowledge Flow
with the `control-plane` service account, to which the same post-install grants the
delegation caller role. Unavailable template
dependencies still prevent their activation. Discovery still fails globally if
an enabled catalog source cannot be reached, including while the pod is starting.

The Control Plane accepts runtime delegation from verified service accounts with
its configured delegation audience and caller role. This matches the pod's
inherited outgoing delegation; the Keycloak `agentic` service account must carry
those claims. User authorization is still resolved for the person on each turn.

For the first chat check, verify the initialized organization default in Models,
then create a Custom assistant without active capabilities. A blank recommended model on the form uses the organization
default when no model is chosen in the chat. Validate a normal text exchange,
a second turn and history after reload before testing reasoning or capabilities.
These are deployment prerequisites, not evidence of a working end-to-end chat.

## Corpus search configuration on k3d

Agent pods search the corpus through Knowledge Flow API, enabled here as the
capability backend. It searches `document-vectors`, the index the worker writes: both are
set in `values-weaver.yaml`, and `k3d/values.yaml` grants those names. Its embedding model is the
shared KF configuration, so queries and chunks use the same vector space.

The API reads with `fred-kf-api` and `fred-ingestion/kf-api-opensearch-password`,
created by the infrastructure chart (`k3d/values.yaml`, `opensearch.identities`). That identity
can read the corpus, its mapping and the hybrid pipeline, but cannot modify corpus
data, mappings or pipelines; its separate logs/KPI permissions keep writes there.

PostgreSQL remains `postgres:5432/fred_weaver`, with login `fred_kf` and schema `knowledge`. The API reads publication and lifecycle facts through `cp_read`; it runs no KF migration. The role writes only knowledge tables and reads publication facts through SELECT-only `cp_read` views.

## Prepare and deploy

From the factory, use `make k3d-app-validate FRED=weaver APP=fred DIR=<this checkout>` to
render or `make k3d-app FRED=weaver APP=fred DIR=<this checkout>` to build and deploy. The
model key must already exist in the `fred-weaver` namespace's
`fred-model-credentials/OPENAI_API_KEY`; the deployment stops before syncing without it.

The seven application deployments are `control-plane-backend`, `knowledge-flow-backend`,
`knowledge-flow-worker`, `frontend`, `fred-agents`, `fred-agents-worker` and `monitor`. The manager image occupies the
chart's `control-plane-backend` key and runs `control-plane serve`; the separate
control-plane worker and the KF SQL migration remain disabled. Manager schema initialization
and Python runtime migrations are enabled. Manager and the Python agent runtime access
PostgreSQL; Control Plane owns permission decisions, and the ingestion worker keeps
its scoped storage credentials.

Everything this profile needs from the backing services is declared in the factory's
`k3d/values.yaml` and applied by `make k3d-up`, by the infrastructure chart and its
post-install Jobs: the database and Temporal namespace, the `fred-ingestion` credentials,
the SeaweedFS identities and manager/input and worker/output policies, the
`app-content-documents` bucket, the worker's OIDC client (audience and claims), and the
scoped OpenSearch accounts of the worker, the Knowledge Flow API and the agent runtime.

The processing contract comes from the worker's own image: with
`workerContract.exportFromWorkerImage`, the chart runs
`knowledge_flow_worker.features.scheduler.export_contract` in an init container of the
control plane, on the worker's ConfigMap, and restarts the control plane when the worker's
image or configuration changes. The dedicated Temporal queue is `manager-ingestion`.

OpenSearch admin credentials stay in the infrastructure, not in the worker or the API. KF receives its
manager service identity, output-only S3 credentials and scoped OpenSearch
credentials. The frontend receives no infrastructure credentials.

This profile does not migrate existing persisted resources. Application data reset
is unsupported for the Rust ingestion profile and is refused before mutation.
Recreating a disposable local installation is a separate operator action.

The vector index is configured in `manager_processing.vector_store.index`. Its name, and
the KPI and log indexes, must match the permissions in the factory's `k3d/values.yaml`.

## PowerPoint preparation worker: configuration and reception

The factory's `k3d-apps/fred/values-weaver.yaml` enables `fred-agents-worker` and
binds runtime `fred-agents` to issuer `http://keycloak:8080/realms/app`, audience
`app`, client `agentic`. Confirm these claims on the actual workload token during
reception; never record the token. Both processes inherit the same content-tagged
image, PostgreSQL capability results, object store and workload Secret references. They use
Temporal namespace `fred-weaver`; the CP supplies their installation-specific
preparation queue. Verify namespace retention exceeds the two-hour deadline.

Use the existing factory commands from [Prepare and deploy](#prepare-and-deploy).
No additional build, chart or local stack is required. The chart's worker has no
HTTP or metrics endpoint: a Kubernetes Ready status is not proof of polling or
completed preparation. Check the CP/worker logs and Temporal poller, then save a
small template through the UI and record its preparation ID and final CP/UI state.

For a deterministic pending state, temporarily set
`applications.fred-agents-worker.replicaCount: 0` in the normal `VALUES` override;
restore it to `1` to resume. A stopped worker before delivery proves waiting, not
interruption of an active preparation. The latter needs an activity observed as
running before stopping its process and observing retry on another replica.

The 5 November 2026 deployment reached seven available workloads with matching
API/worker images, verified workload claims and active Temporal pollers. The chart
also mounts its generated processing contract only in the Deployment, so migration
Jobs no longer inherit an undefined volume. Keep the updated factory overlay and
chart together. The developer then took over reinstallation and reception before
bootstrap. Office conversion, worker recovery and all browser scenarios remain
unverified. Do not perform inference merely to validate deployment: the profile uses
Mistral, and the embedded test provider is not yet wired through Weaver's catalog.
See the [operator note](../release-notes/changes/weaver-powerpoint-file-ownership.md)
and the existing porting status for the reception boundary.

## Models for local testing

The profile declares the `mistral` source in the control plane, using
`https://api.mistral.ai/v1/models` for discovery and
`https://api.mistral.ai/v1` for inference. This local profile explicitly reuses
the existing `fred-model-credentials/OPENAI_API_KEY` for both operations; no
secret value is stored in the configuration. The control plane uses the same
node CA bundle as the pod for outgoing TLS.

The overlay explicitly assigns `mistral` to the demo organizations `Acme` and
`Globex`, resolved by their exact PostgreSQL names after the existing provisioning
import. Each initially permits `mistral-small-latest` and `mistral-medium-latest`,
selects Small as default, and leaves fallback/reasoning empty. The test account is
shared deliberately; distinct accounts require distinct source IDs. Other
organizations need their own explicit declaration, never an implicit global grant.

Provision secrets, deploy the schema/configuration, then import the existing demo
bundle. The post-provisioning pass discovers and initializes models automatically.
Successful initialization is durable: restarts preserve subsequent UI decisions,
even an empty or deleted policy. Missing models/discovery failures grant nothing
for that organization. Correct the dependency and replay `control-plane
initialize-models` in the manager's environment; already completed organizations
are untouched. For historical policies, supply all source mappings explicitly;
their administered choices are preserved. See the [initialization contract](../../apps/control-plane/README.md#initialize-organization-models-once)
for diagnostics, bounds and recovery.

Discovery lists the provider's complete visible inventory and grants no access.
Later discoveries do not extend the explicit permitted list. The old factory
`models_catalog` remains excluded from this Weaver overlay. The isolated automated
tests do not establish real k3d/provider validation; that remains a developer check.

The host equivalent is `apps/control-plane/config/configuration_prod.yaml`, with the
existing Mistral key supplied through the control plane's environment or local
`.env`. The pod's `configuration.yaml` and `configuration_prod.yaml` retain only
the matching inference credential binding.

`fred-test-mock` is a separate follow-up: retain the embedded pod model used by
the graph Test agent, and wire it through Weaver's catalog and authorization.
Do not replace it with the separate HTTP benchmark mock. This increment does
not expose or activate the embedded mock.

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

## Independent Knowledge Flow applications

The build hook produces distinct API and worker image references. The worker's
`knowledge_flow_worker.features.scheduler.export_contract` exports Temporal policy
inside that image, without installing or importing the API. All extraction groups
inherit the worker image; optional PyMuPDF affects only that image.

The API keeps its service and routes. Its configuration has `published_artifacts`,
`use_gpu` and `text_splitter`; processing profiles and Temporal configuration live
only in the worker. The existing `fred_kf` role, E0 schemas and grants are unchanged.
This packaging split has not yet been built or validated end to end.
