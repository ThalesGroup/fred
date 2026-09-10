## Why

Fred can pull documents from a remote source today only as deployment YAML:
`document_sources` maps a `source_tag` to a provider config read from the
knowledge-flow configuration file, with secrets from environment variables. It
has no team, no instance, no schedule and no user-visible run state. A third
party cannot ship a source of their own, and a team cannot point one at its own
endpoint on its own cadence.

Two outcomes, narrowly scoped, define this change.

**For the user.** A Platform Admin sees the Knowledge Base definitions
configured in this deployment and enables one for a team. A member of that team
creates a Knowledge Base instance, fills in a form Fred renders from the
definition's declared fields, chooses a schedule in plain terms — "every
Thursday at 05:00 Europe/Paris" — and thereafter sees when it last ran, whether
it succeeded, and what it changed. Disabling the instance suspends it; deleting
it removes it.

**For the SDK author.** Someone outside this repository writes a declaration and
one asynchronous synchronization handler. They never learn what a workflow, an
activity, a task queue, a retry policy or a schedule object is. Their pod dials
out to Temporal and to Fred; nothing reaches into it, and it exposes no HTTP
service.

## Configured is not online

A Knowledge Base definition is **configured in the Control Plane deployment**.
Being configured means exactly three things: the Platform Admin can see it, the
Platform Admin can enable it for a team, and members of an enabled team can
create instances from it.

It does not mean a pod was discovered, a worker is connected, the Knowledge
Base is healthy, or that Fred has checked Temporal worker availability. Fred
performs no such check, and the UI must not present a configured definition as
online. A definition whose pod is not running produces scheduled executions
that time out observably according to the configured Temporal timeouts —
failure surfaces at run time, not at enablement or instance creation.

This is a deliberate reduction from an earlier draft of this change, which
proposed a runtime registration endpoint and pod-start upsert. There is no
registration endpoint, no startup register call, no catalog discovery, and no
Kubernetes HTTP service for the KB pod.

## What Changes

**Definition installation.** The SDK author's declaration can produce a
JSON-safe manifest artifact. An operator installs that artifact through the
Control Plane deployment configuration. Control Plane validates every
configured definition at startup. A configured definition carries enough to
derive or resolve its identity and version, its display metadata, its instance
configuration fields, the expected dedicated M2M client identity, and its
internal execution routing. Temporal task queues and every other Temporal value
stay internal — never chosen or manipulated by an SDK author or a Fred user.

**Author-facing contract (fred-sdk, public).** A declaration carrying
identifier, version, display metadata and one list of instance configuration
fields declared with the existing `FieldSpec` vocabulary; a decorator
registering exactly one synchronization handler; a context handed to that
handler; a bounded result returned from it; and a run entry point that starts
the pod's worker. No Temporal type or term appears in this surface, though
fred-sdk depends on `temporalio` internally.

**Execution.** Control Plane owns a typed, user-facing recurrence and
translates it into a Temporal Schedule that starts an SDK-provided generic
workflow on the definition's task queue. The workflow input carries stable
identifiers only; a run identifier is derived internally when the workflow
starts rather than frozen into the schedule. An SDK-provided activity adapter
fetches that run's configuration from Control Plane over the pod's own
confidential M2M client, invokes the handler, and reports the terminal state
and bounded result back.

**Storage boundary.** A Knowledge Base implementation never receives OpenSearch
or S3/SeaweedFS credentials through the Fred SDK contract. It writes through an
authenticated Knowledge Flow document boundary, scoped to the current team and
instance. Source credentials and Fred credentials stay separate: the WebDAV or
HTTP token is instance configuration used only against the external source; the
M2M token is the pod's workload identity used only against Fred APIs.

## Responsibilities

| Control Plane | fred-sdk runtime | KB pod / implementation |
| --- | --- | --- |
| Configured KB definitions, validated at startup | Author-facing declaration and handler API | Hosts the SDK's Temporal worker |
| Platform Admin visibility, team enablement | Produce the JSON-safe manifest artifact | The synchronization handler |
| Team-scoped instances and their configuration | Start the worker; own task-queue identity | HTTP/WebDAV access, Markdown parsing |
| Typed periodic schedules and their lifecycle | Generic workflow + activity adapter | Discovery and filtering |
| Temporal Schedule creation and management | Fetch run context; invoke handler | Change detection, hashes, ETags, cursors |
| Run records and bounded run results | Report terminal state and result | Reconciliation decisions |
| Authenticated run-context and result endpoints | Heartbeat, cancellation, retry plumbing | Source credentials and source state |

Knowledge Flow owns the supported Fred document ingestion and storage boundary,
isolation of stored documents, and the OpenSearch and S3/SeaweedFS integration
behind it.

## Capabilities

### New Capabilities

- `knowledge-base-contract`: how a Knowledge Base definition is declared and
  configured into a deployment, made available to a team, instantiated and
  scheduled, dispatched to its worker, authorized at run time, and reported on.

### Modified Capabilities

None. No existing capability spec changes.

## Impact

Affected areas, none of which exists yet:

- **`libs/fred-sdk`** — the author-facing Knowledge Base package, the manifest
  artifact producer, and the runtime that starts a worker and adapts the generic
  workflow onto the developer's handler.
- **`apps/control-plane-backend`** — configured-definition parsing and startup
  validation, team enablement over those definitions, instance storage and
  configuration validation, the typed schedule and its Temporal Schedule
  lifecycle, run records, and the authenticated run-context and result-reporting
  endpoints.
- **Persistence** — new tables for instances and runs, therefore an Alembic
  migration in control-plane.
- **Generated API client** — new control-plane controllers change the OpenAPI
  spec, so the frontend client is regenerated in the same change.
- **Knowledge Flow** — the minimum authorized document boundary a KB runtime
  writes through. Whether today's push APIs already satisfy it is a question
  this change answers with one focused investigation task, not a redesign.

Explicit non-goals:

- No runtime registration endpoint, pod discovery, liveness registry or
  "online" status anywhere in the product.
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
- No Kubernetes autoscaling, scale-to-zero or start-pod-at-schedule-time.
- No inbound HTTP service on the KB pod.
- No raw Temporal object or term in the public author-facing API.
- No asynchronous callback or job protocol for long runs in the MVP.
- **The WebDAV/Markdown synchronizer is not part of this change.** It is an
  external experiment that will consume the published contract and validate it
  afterwards.
- `#2240` keeps ownership of the externally-deployed-provider ingestion
  execution contract.
