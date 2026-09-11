## Why

Fred can pull documents from a remote source today only as deployment YAML:
`document_sources` maps a `source_tag` to a provider config read from the
knowledge-flow configuration file, with secrets from environment variables. It
has no team, no instance and no user-visible run state. A third party cannot ship
a source of their own, and a team cannot point one at its own endpoint.

Two outcomes, narrowly scoped, define this change.

**For the user.** A Platform Admin sees the Knowledge Base definitions available
in this deployment and enables one for a team. A member of that team creates a
Knowledge Base instance and fills in a form Fred renders from the definition's
declared fields, then sees when it ran, whether it succeeded, and what it
changed.

**For the SDK author.** Someone outside this repository writes a declaration and
one asynchronous synchronization handler, and deploys an image that publishes
itself and serves runs. They never learn what a workflow, an activity, a task
queue or a retry policy is. Their pod dials out to Temporal, to Fred and to
Knowledge Flow's REST API; nothing reaches into it, and it exposes no HTTP
service.

## Published is not online

A Knowledge Base definition exists in a deployment because **the image
implementing it published a declaration**. Existing means exactly three things:
the Platform Admin can see it, the Platform Admin can enable it for a team, and
members of an enabled team can create instances from it.

It does not mean a pod was discovered, a worker is connected, the Knowledge Base
is healthy, or that Fred has checked Temporal worker availability. Fred performs
no such check, and the UI must not present a definition as online. A definition
whose pod is not running produces runs that time out observably according to the
configured Temporal timeouts — failure surfaces at run time, not at enablement or
instance creation.

Publication is the **single write at deployment**: one outbound call from the
deployed image, on a deployment hook, stamped with the image's version. There is
no Knowledge Base entry in Control Plane configuration, no catalog discovery, and
no Kubernetes HTTP service for the KB pod. The first publication for a definition
binds it to the publishing client; a later one must present the same client.

A stored declaration says an image was deployed and what shape of configuration
it expects. It never expires, is never deregistered, and is never read as
evidence that a pod is running.

## What Changes

**Definition installation.** One write, at deployment. The deployed image posts
its own declaration — identity, display metadata, version and instance
configuration fields — outbound on a `post-install,post-upgrade` hook, and Fred
stores it against the definition id. There is no Knowledge Base entry in Control
Plane configuration and no inline copy anywhere, so the form Fred renders always
matches the image that is deployed. The first publication binds the definition to
its publishing client, and that binding authorizes every later call. Execution
routing is derived from the definition id on both sides rather than stated
anywhere. Temporal task queues and every other Temporal value stay internal —
never chosen or manipulated by an operator, an SDK author or a Fred user.

**Author-facing contract (fred-sdk, public).** A declaration carrying
identifier, version, display metadata and one list of instance configuration
fields declared with the existing `FieldSpec` vocabulary; a decorator
registering exactly one synchronization handler; a context handed to that
handler; a bounded result returned from it; and two entry points — one
publishing the declaration, one starting the pod's worker. No Temporal type or
term appears in this surface, though fred-sdk depends on `temporalio`
internally.

**Execution.** A run starts an SDK-provided generic workflow on the definition's
derived task queue. The workflow input carries stable identifiers only; a run
identifier is derived internally when the workflow starts. An SDK-provided
activity adapter fetches that run's configuration from Control Plane over the
pod's own confidential M2M client, invokes the handler, and reports the terminal
state and bounded result back.

**Ingestion.** A Knowledge Base implementation never receives OpenSearch or
S3/SeaweedFS credentials through the Fred SDK contract. It ingests and deletes
documents through the REST API Knowledge Flow already exposes. Source
credentials and Fred credentials stay separate: the WebDAV or HTTP token is
instance configuration used only against the external source; the M2M token is
the pod's workload identity used only against Fred APIs.

## Responsibilities

| Control Plane | fred-sdk runtime | KB pod / implementation |
| --- | --- | --- |
| Stored published declarations and their client binding | Author-facing declaration and handler API | Hosts the SDK's worker; publishes on deploy |
| Platform Admin visibility, team enablement | Publish the declaration; define the pod's environment contract | The synchronization handler |
| Team-scoped instances and their configuration | Start the worker; derive task-queue identity | HTTP/WebDAV access, Markdown parsing |
| Run records and bounded run results | Generic workflow + activity adapter | Discovery and filtering |
| Authenticated publication, run-context and result endpoints | Fetch run context; invoke handler | Change detection, hashes, ETags, cursors |
| | Report terminal state and result | Reconciliation decisions |
| | Heartbeat, cancellation, retry plumbing | Source credentials and source state |

Knowledge Flow owns document ingestion through its REST API, isolation of stored
documents, and the OpenSearch and S3/SeaweedFS integration behind it.

## Capabilities

### New Capabilities

- `knowledge-base-contract`: how a Knowledge Base definition is declared and
  published into a deployment by its own image, made available to a team,
  instantiated and configured by that team, dispatched to its worker, authorized
  at run time, and reported on.

### Modified Capabilities

None. No existing capability spec changes.

## Impact

Affected areas, none of which exists yet:

- **`libs/fred-sdk`** — the author-facing Knowledge Base package, the
  declaration's JSON-safe publication payload, the `publish` and run entry
  points, and the runtime that starts a worker and adapts the generic workflow
  onto the developer's handler.
- **`apps/control-plane-backend`** — stored published declarations and their
  client binding, team enablement over those definitions, instance storage and
  configuration validation, run records, and the authenticated publication,
  run-context and result-reporting endpoints. The configured-definition parsing
  and startup validation built earlier in this change are deleted, not extended.
- **Persistence** — new tables for published declarations, instances and runs,
  therefore Alembic migrations in control-plane.
- **Generated API client** — new control-plane controllers change the OpenAPI
  spec, so the frontend client is regenerated in the same change.
- **Knowledge Flow** — none. A KB pod uses the REST API that already exists.
  What that API turns out to lack is an expected output of this change, recorded
  and scoped separately rather than fixed here.

Explicit non-goals:

- No pod discovery, liveness registry or "online" status anywhere in the
  product. A pod publishes a declaration at deployment; it never reports that it
  is running, and Fred never asks.
- **No recurring schedules.** Typed daily/weekly recurrence, time zones,
  suspend/resume and overlap policy are deliberately out. An instance carries
  configuration and runs, not a cadence. The scheduling surface is scoped as its
  own change once this one has shown what Knowledge Flow's REST API needs from a
  pod that really ingests.
- **No new Knowledge Flow ingestion boundary.** An implementation uses the REST
  API Knowledge Flow already exposes; whatever it enforces is what is enforced.
- **No reconciliation of a changed declaration against existing instances.** A
  version whose declared fields differ is deployed only after its instances have
  been deleted. Fred implements no detection, migration or degraded instance
  state for it.
- No ingestion or delivery redesign, and **no synchronization ledger**. Source
  document identity, source version history, revisions, ETags and hashes,
  mappings to Fred document UIDs, cursors, tombstones, the last successful
  inventory and every reconciliation decision belong exclusively to the
  implementation, which persists them wherever it chooses — Git, PostgreSQL,
  S3, SQLite on a persistent volume or anything else. Fred owns only the
  current materialized document projection; Fred and Temporal own run lifecycle
  and bounded run summaries. Temporal workflow history is not a synchronization
  database and SHALL NOT be used as one.
- No direct OpenSearch or S3/SeaweedFS access in the portable contract.
- No Kubernetes autoscaling or scale-to-zero.
- No inbound HTTP service on the KB pod.
- No raw Temporal object or term in the public author-facing API.
- No asynchronous callback or job protocol for long runs in the MVP.
- **The WebDAV/Markdown synchronizer is not part of this change.** It is an
  external experiment that will consume the published contract and validate it
  afterwards.
- `#2240` keeps ownership of the externally-deployed-provider ingestion
  execution contract.
