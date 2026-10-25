# Weaver: local ingestion deployment and agent catalog preparation

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

## Agent catalog preparation: activation blocked

`deploy/k3d/build` also builds `apps/fred-agents` through its existing
`docker-build` target. The same content-derived `k3d-<digest>` tag is written to
`images.txt` and to `images.yaml` under the `fred-agents` consumer. Build output
is still published only after all four images succeed. Building this image does
not enable its deployment.

The chart confirms Service `fred-agents`, port 80 targeting container port 8000,
and HTTP prefix `/fred/agents/v2`. Rust appends `/agents/templates`; that public
route lists public registry definitions by default without calling the control
plane or invoking a model. The existing organization Agents UI consumes the Rust
catalog. No UI change or runtime registration is needed.

**Do not enable the inherited Swift runtime profile yet.** Source inspection
found two startup contracts incompatible with a Weaver-only installation:

- `enforce_account_status` requires OpenFGA `organization.suspended: [user]`.
  Weaver uses `space` and has no such type/relation. The inherited Python defaults
  select store `fred`, allow store creation and synchronize the Swift model at
  startup. Pointing those defaults at Weaver's store would publish the wrong
  model; using a separate Swift store would not enforce Weaver's authority.
- With user, M2M and ReBAC security enabled, `initialize_platform_access` requires
  the legacy Python tables `platform_access_settings`, `platform_access_users`,
  `platform_access_removals`, `users`, `teammetadata`, `platform_access_links` and
  `platform_access_link_joiners`, and reads them at startup. Weaver migrations
  do not provide that admission contract. Runtime/capability migrations do not
  replace the Python control-plane migrations.

These checks precede serving even the public catalog. Disabling authentication,
ReBAC or delegation, creating a parallel authority, installing legacy manager
migrations, or replacing the OpenFGA model is not a deployment-only solution.
A separate runtime/authorization adaptation must define how the pod retains
Weaver's admission and authorization guarantees before activation.

The following inherited dependencies also become active with `fred-agents`:

| Dependency | Inherited behavior |
| --- | --- |
| Migrations / PostgreSQL | Factory enables the pre-upgrade runtime and installed-capability migration job, including scale-down; runtime requires durable SQL and `session_history` at startup. Database `fred`, user `fred`, host `postgres`; password from `fred-secrets/POSTGRES_FRED_PASSWORD`. |
| OpenFGA | `http://openfga:9080`, token from `fred-secrets/OPENFGA_API_TOKEN`; unsafe default store creation/model synchronization must be resolved before activation. |
| Keycloak | C3, user and M2M authentication, outgoing delegation; client `agentic`, secret `fred-secrets/KEYCLOAK_AGENTIC_CLIENT_SECRET`. Factory infrastructure provisions this client and its service/delegation roles; checkout identities only add the ingestion worker. Secondary realm/origins are inherited. OpenAI-compatible execution is already disabled. |
| Storage / observability | SeaweedFS runtime object store with inherited admin credential `fred-secrets/SEAWEEDFS_ADMIN_PASSWORD`; OpenSearch logs with `fred-secrets/OPENSEARCH_PASSWORD`, Prometheus metrics, and the node CA mount. This does not reuse the ingestion worker's scoped credentials. |
| Models | Mounted Mistral and in-process mock profiles; required `fred-model-credentials/OPENAI_API_KEY`. Web research remains disabled and its provider Secret optional. Catalog discovery makes no LLM request. |
| Legacy APIs | Startup creates a lazy control-plane HTTP client. Managed execution later calls the legacy team/agent-instance runtime binding; discovery does not. Knowledge Flow HTTP is disabled in this profile, so its legacy tools are not established either. |

`applications.fred-agents.enabled` therefore remains false and no external Rust
source is activated. Once the startup contract is resolved, the intended addition
belongs in this checkout's `values.yaml.gotmpl`, alongside enabling the pod:

```yaml
applications:
  control-plane-backend:
    configuration:
      platform:
        runtime_catalog_sources:
          - runtime_id: fred-agents
            base_url: http://fred-agents/fred/agents/v2
            enabled: true
```

The base/secondary adapters continue to drop factory control-plane configuration;
no Rust configuration moves to the factory. Discovery still fails globally if
any enabled source fails, including the organization list containing Ralph.
The refusal to activate templates with unavailable dependencies is unchanged.

After resolving the blocker and deploying, Dimi validates with `o1admin`:
organization administration -> Agents shows Ralph and the public fred-agents
templates, including after reload. This proves catalog discovery only, not
instance creation or execution. No dynamic validation, tests, builds or deployments
were run for this preparation; the current diff cannot yet satisfy that criterion.

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

The three application deployments are `control-plane-backend`, `knowledge-flow-worker`
and `frontend`. The manager image occupies the chart's `control-plane-backend`
key and runs `control-plane serve`; the separate control-plane worker, KF HTTP
API, its SQL migration and Fred Agents are disabled. The manager's own SQL
migration remains enabled. Only manager accesses PostgreSQL and OpenFGA.

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
