---
schema: 1
title: "Prepare CP-owned PowerPoint templates durably on their logical agent pod"
impact: minor
configuration: production
configuration_reason: "Configure a distinct workload identity for each logical pod and run its existing application image in worker mode against the shared capability database and Temporal."
---

## Applicability

New installations of Weaver Control Plane, fred-runtime, fred-agents, the installed
ppt_builder library and frontend. This supersedes the configurable platform default described in
ppt-builder-capability.md. A capability remains an installed library of a logical
pod. An organization default is scoped to `(organization, logical pod)`; different
pods can use different library versions and templates. Replicas of one logical
pod share its queue and capability results. Knowledge Flow is not involved.

## Prerequisites

Use the same PostgreSQL database for CP and runtime/capability tables, with their
separate roles. Provide the configured object storage and Temporal services.
API and worker replicas of one logical pod must share capability storage.

## Upgrade

Only fresh installations are supported. Run the normal CP initialization hook
through the complete SQLx migration chain. API startup verifies migrations; it
does not apply them. No live database operation accompanies this source change.

Run the installed capability migrations with `python -m fred_runtime migrate`
using the target pod image and its SQL configuration. The preparation path reuses
cap_ppt_builder_analysis; its preparation receipts are keyed by opaque preparation
identity, retain attempt leases and become tombstones when retired.

## Configuration

The CP continues using existing content storage, transfer limits, quotas and
cleanup. Configure the approved runtime source as before and bind its workload:

```yaml
platform:
  capability_preparation:
    workers:
      fred-agents: # exact runtime_catalog_sources runtime_id
        issuer: https://iam.example/realms/app
        audience: app
        client_id: fred-agents
```

Use the actual verified token claims. The workload token must contain the CP
accepted audience; a browser token, a service-account username by itself, or an
arbitrary preparation UUID is insufficient. Different logical pods must have
different issuer/client identities. Ordinary space write permissions govern file
changes; platform/organization administrator status does not grant content rights.

The CP dispatcher reuses `scheduler.lifecycle.temporal` connection, namespace and
RPC limits. Capability preparation does not require enabling the separate space
lifecycle scheduler. Accepted work continues to expire/reconcile even if new
preparation admission is subsequently disabled. Temporal retention must exceed
the two-hour preparation deadline; connection validation checks that horizon.

Use the same application image and installed capability packages as the pod API:

```sh
ENV_FILE=/path/to/worker.env python -m fred_agents --mode worker
```

The worker configuration keeps the same `app.runtime_id`, `platform.control_plane_url`,
`security.profile: c3`, M2M credentials and shared PostgreSQL capability storage as
that logical pod. Enable `scheduler.enabled` in the worker configuration and point
`scheduler.temporal.host` and `namespace` at the same Temporal installation as the
CP. The effective queue is returned by the CP from the storage installation UUID
and logical pod; neither a browser nor `scheduler.temporal.task_queue` chooses it.
Keep API mode's existing scheduler configuration unless independently needed.

API remains the default (`python -m fred_agents`). Worker mode initializes SQL,
the capability registry, workload credentials and shared HTTP client; it does not
start the HTTP server, conversation stores, agent loop or conversation workflows.
It runs at most two preparation activities concurrently. SIGINT/SIGTERM initiates
Temporal shutdown and closes its resources. Worker logs go to stdout, like those of
every Fred process. Each preparation appears by its identifier in `operation_id`,
with exception types and HTTP statuses but no messages or bodies.
The CP logs its delivery, failure and Temporal outage under the same identifier.

The Fred chart exposes this as `applications.fred-agents-worker.enabled: true`
(disabled by default). Its `inheritFrom: fred-agents` resolves after image and
instance overrides: configure image, runtime ID, SQL, CP URL and workload secrets
on the API only. Separate worker image/credentials/storage are rejected by the
chart schema. Its scheduler is enabled independently without changing API mode.
The chart also refuses a missing CP workload binding or a different Temporal
host/namespace. Only the API's migration hook upgrades runtime and installed
capabilities, after CP schema initialization; the worker has no migration hook.

The worker Deployment has no network service, ingress, metrics endpoint, API
probe or Kubernetes RBAC. Startup failures exit and are restarted by Kubernetes;
an apparently Ready container still requires checking the actual Temporal poller
and one preparation. Its 60-second termination grace covers the runtime's
30-second shutdown budget. Initial per-replica limits are 2 CPUs, 2 GiB memory
and 2 GiB ephemeral storage for two concurrent activities, not a capacity claim.
Tune resources only from observed files. Set worker `replicaCount: 0` to pause
without stopping the API, and restore it to resume preparation and cleanup.

For local Weaver, use the existing factory profile, which binds `fred-agents`
to the `agentic` workload and namespace `fred-weaver`. From fred-deployment-factory:

```sh
# Offline rendering; does not deploy or migrate.
make k3d-app-validate FRED=weaver APP=fred DIR=/absolute/path/to/weaver/fred
# Developer-run build/deployment, after checking the dedicated target and secrets.
make k3d-app FRED=weaver APP=fred DIR=/absolute/path/to/weaver/fred
```

The factory values change and the Fred chart change must be used together. Existing
image overlays for `fred-agents` also reach the worker, without another image key.
The configured `app` audience must be verified against actual claims during
reception. The deployment keeps the existing provider configuration: it does not
authorize a paid inference call or introduce a mock provider.

## Accepted saves and availability

For an agent, PUT first stages an immutable original using Idempotency-Key and
expected_file_id. A new agent draft also names its approved template. The following
agent save performs bounded capability preflight before its SQL transaction. That
transaction accepts configuration, attaches the staged file and records the exact
preparation intention together. Refusal leaves the previous accepted configuration
and analysis intact. Unaccepted uploads expire through the existing sweeper.

An accepted own-template save or replacement displays preparation in the card and
editor. CP runtime admission refuses new exchanges, including direct pod calls,
until the worker's result is acknowledged. The worker reads canonical context and
bytes with its own identity, verifies their digest, invokes the installed library,
commits the result, then confirms the exact preparation to CP. The Temporal payload
is only a preparation UUID; no file or browser credential enters history.

Confirmation is idempotent and checks the current file, revision and preparation.
A restart after result storage reuses it and reconfirms. A closed workflow without
confirmation, exhausted retries, or a missing worker becomes an explained failure;
the CP deadline also works when Temporal is unavailable. Structural analysis and
preview generation reuse the library's existing bounded execution and SQL fences.
Readiness is consultation only; opening a form never launches or repairs analysis.
Vision outside an admitted conversation remains explicitly unavailable.

For organization defaults, PUT accepts a candidate for the selected logical pod
after preflight. The preceding effective template remains in use until success;
failure retains it, or the built-in template when absent. Own agent templates are
unaffected. Resolution is own agent → organization on this pod → built-in. Removing
an own attachment invalidates its preparation and restores this resolution.
The Features page exposes the organization template under its selected pod only
when the person also has space write access.

## Concurrency and cleanup

SQL intentions, replay identities, compare-and-swap replacement and organization
locks govern acceptance. Temporal delivery uses the existing bounded transport
and durable SQL leases without borrowing ingestion tables. No conversion, analysis
or network operation occurs inside an acceptance transaction. Obsolete, failed or
wrong-revision results cannot mark a newer agent ready. The owning pod verifies
result references; preview reads also resolve the current authorized usage via CP.
That preview lookup uses the shared person credential provider and explicitly
disables client-default HTTP authentication, preserving the requesting person's
identity rather than substituting workload credentials.

Originals and transfers retain the existing local quotas shared with documents
and attachments. Superseded bytes awaiting purge are excluded from logical usage;
this does not activate the separate storage_budget organization-total preparation.
Keep the S3 sweeper and each owning capability worker available for cleanup.
Obsolete preparation receipts survive owner deletion; the worker clears their
binaries, inventory and thumbnails, retaining a tombstone that fences late writes,
including a delayed first activity. Space deletion waits for original and derived
cleanup acknowledgements. A missing owning worker leaves cleanup visibly pending.

## Limitations

Following the scope decision for this increment, the agent turn remains unchanged:
no per-tool reauthorization, durable per-turn template lease or new interruption
protocol. New exchanges are gated by CP. A replacement or removal during an
already admitted turn can make its former template unavailable during cleanup.
Resolving that edge case belongs to a subsequent, cross-resource turn-lifecycle
review. This increment does not claim to preserve every in-flight resource usage.
Conversations and presentation plans are outside its purge scope. Template
preparation and presentation generation remain separate operations.

## Validation

Local checks cover disposable PostgreSQL/SeaweedFS acceptance, draft creation,
SQL ownership constraints, rejection without replacement, replay, concurrent
replacement, organization candidate activation, pod isolation, late confirmations and cleanup. A disposable
Temporal test restarts the worker after persisted result/failed confirmation; a
separate CP delivery test checks uncertain-delivery replay and terminal reconciliation.
Python and frontend tests cover preparation fences, CP admission, readonly readiness,
worker/API entrypoints and state after reload. Contracts are generated from source.
See WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md for the exact final commands and results.

The initial deployment wiring was checked offline: chart schema regeneration,
values validation and rendering cover image/SQL/credential inheritance, worker-only
mode, migration order, pause at zero replicas and refusal of divergent worker
configuration. This adds no runtime acceptance evidence to the application tests
above. No cluster or database mutation was performed during that initial wiring.

On 5 November 2026, the authorized local deployment used the existing factory
profile on `k3d-fred` / `fred-weaver`. The initially empty database was backed up
before the normal initialization hooks. A first-install defect was corrected:
the generated processing-contract volume is now mounted by the Deployment itself,
not through application extra mounts inherited by migration Jobs. Remove that
explicit mount from overlays using `workerContract.exportFromWorkerImage`; the
updated factory values and chart example already do so. No migration was edited.

Release `fred-app` revision 2, chart 5.0.0, reached seven available Deployments.
All seven SQLx checksums match source; runtime/capability migrations succeeded.
API and worker run the same `fred-agents:k3d-d5ef1437f5b8223e` image and executed
digest. The actual workload issuer/audience/client match the CP binding, Temporal
retention is 72 hours and both preparation pollers are present on the CP-returned
queue. LibreOffice 24.2.7.2 is installed. Four focused worker/chart tests, the
schema-init Secret regression, Helm lint/render and Kubernetes server dry-run
validation passed. Exact image references are in the existing porting status.

The browser reached the bootstrap screen after login. The developer then explicitly
took over reinstallation, bootstrap and functional reception. Bootstrap and CGU
acceptance were not performed; all seven user scenarios remain unverified.
Office conversion was not exercised: a standalone diagnostic stopped on its own
unavailable `fitz` import before invoking LibreOffice. No provider inference,
test-agent creation, cleanup, data reset, commit or push was performed.

Deployment checks are not end-to-end acceptance. Receive the full browser
→ CP → actual pod API/worker → PostgreSQL/S3/Temporal journey on matched images,
including ingress, workload claims, actual Office conversion and worker shutdown.
Local k3d reception, once supplied by the developer, will still not
establish reception on the integration platform or qualify this journey for arc42.

## Rollback

Migration to or from an older Weaver version is unsupported. Retain the owning
workers and storage sweeper until obsolete results/originals are cleaned.
