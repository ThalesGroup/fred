# Knowledge Base Contract Specification

## Purpose

Defines how a Knowledge Base definition is declared by an SDK author, published
into a Fred deployment by its own image, made available to a team, instantiated
and configured by that team, dispatched to its worker, authorized at run time,
and reported on — so that a domain developer writes only a synchronization
handler and a team controls its own configuration.

## Requirements

### Requirement: Definitions exist because their image published them, and existence is not a liveness signal

A Knowledge Base definition SHALL exist in a deployment only because the image
implementing it published a declaration to Control Plane. Control Plane
deployment configuration SHALL carry no Knowledge Base entry of any kind.

The first publication for a definition identity SHALL bind that definition to
the publishing client's identity. A later publication for the same identity
SHALL be refused unless it presents the same client. This binding is the only
thing preventing one workload from overwriting another's declaration, so it
SHALL NOT be satisfied by membership of a broad service role.

Existence SHALL mean only that the definition is visible to a Platform Admin,
may be enabled for a team, and may be instantiated by an enabled team. It SHALL
NOT imply that a pod exists, that a worker is connected, or that the Knowledge
Base is reachable. Fred SHALL NOT check worker availability, and no surface
SHALL present a definition as online.

#### Scenario: First publication binds the definition to its client

- **WHEN** a definition identity is published for the first time
- **THEN** the definition exists, and the publishing client is recorded as the
  only client that may publish that identity again

#### Scenario: Another client cannot take over a definition

- **WHEN** a client publishes a declaration for a definition identity already
  bound to a different client
- **THEN** the request is refused, and holding a broad service role does not make
  it succeed

#### Scenario: A published definition is not reported as online

- **WHEN** a Platform Admin views a definition whose pod is not running
- **THEN** the definition is shown as available, with no claim about
  connectivity, health or worker presence

### Requirement: Declarations are published by the definition's own image

A definition's declaration SHALL be published by the image that implements it,
through an outbound call to Control Plane, and publishing SHALL be the only way
a declaration reaches Fred. Publication SHALL be a deployment step rather than a
side effect of executing a run: the image SHALL expose one command that
publishes the declaration and one that serves runs, and the publishing command
SHALL terminate, reporting success or failure through its exit status. It SHALL
run on every deployment of the image, so that what Fred stores is what is
deployed. There SHALL be exactly one way to publish.

Publication SHALL be an idempotent upsert keyed by definition identity, stamped
with the published version, so repeating it leaves exactly one stored
declaration.

Publishing SHALL NOT require any inbound network service on the Knowledge Base
pod, and Fred SHALL NOT read a declaration from the pod. A stored declaration
SHALL NOT expire, SHALL NOT be deregistered, and SHALL NOT be presented or
interpreted as evidence that a pod exists or a worker is running.

A definition's declared configuration fields SHALL be treated as fixed for the
lifetime of its instances. Deploying a version whose declared fields differ
while instances still exist is outside the supported operation of this contract:
the supported sequence is to delete those instances first. Fred SHALL NOT
detect, reconcile, migrate or mitigate such a change, and SHALL NOT hold state
describing one.

#### Scenario: Publishing and serving are separate commands

- **WHEN** the image is run with its publishing command
- **THEN** the declaration is posted to Control Plane, the command terminates
  with a success exit status, and no worker is started

#### Scenario: Publication is an idempotent upsert

- **WHEN** a declaration is published, and later published again unchanged, and
  later still published with changed display metadata
- **THEN** exactly one stored declaration exists for that definition throughout,
  unchanged by the repeat and replaced and restamped by the change

#### Scenario: Changing declared fields is an operator sequence, not a Fred behaviour

- **WHEN** a definition's instances are deleted and a version declaring
  different configuration fields is then deployed and published
- **THEN** the stored declaration is replaced, and Fred holds no record of the
  previous fields and performs no reconciliation of its own

### Requirement: Platform Admin visibility and team enablement

A published definition SHALL be visible to a Platform Admin on a surface
dedicated to Knowledge Bases, who alone may enable it for a team. A definition
SHALL NOT be usable by a team until enabled for that team. Enablement SHALL be
an availability decision only and SHALL store no configuration values. Disabling
SHALL prevent creation of new instances for that team.

The Platform Admin surface SHALL present a definition's identity and its
enablement state only. A definition's declared configuration fields SHALL NOT
appear on it, in any form, since that surface neither collects nor stores a
configuration value.

A Knowledge Base definition SHALL be authorized as its own resource type. It
SHALL NOT appear in the agent capability catalog or the application catalog, and
a grant on an agent capability or an application SHALL NOT make a Knowledge Base
usable.

#### Scenario: The admin surface offers enablement and nothing else

- **WHEN** a Platform Admin views the published definitions for a team
- **THEN** each definition shows its identity and whether it is enabled, and
  neither its declared configuration fields nor any count or summary of them is
  presented

#### Scenario: Definition is unusable before enablement

- **WHEN** a definition is published but not enabled for a team
- **THEN** a member of that team cannot create an instance of it

#### Scenario: Enablement grants availability without storing configuration

- **WHEN** a Platform Admin enables a definition for a team
- **THEN** members of that team can create instances of it, and no configuration
  values are recorded by the enablement itself

#### Scenario: Definitions stay out of the capability and application catalogs

- **WHEN** the agent capability catalog and the application catalog are listed
- **THEN** no Knowledge Base definition appears in either, and no grant on an
  agent capability or an application makes a Knowledge Base usable

### Requirement: Team-scoped instances, more than one per definition

A team SHALL be able to create more than one instance of the same enabled
definition, each carrying its own configuration and run history. Every instance
SHALL belong to exactly one team, and its configuration and runs SHALL be
accessible only within that team.

#### Scenario: Two instances of one definition coexist

- **WHEN** a team creates two instances of the same definition with different
  configuration values
- **THEN** both exist independently with their own run histories, and neither
  overwrites the other

#### Scenario: Another team cannot reach an instance

- **WHEN** a user outside the owning team attempts to read, modify or list runs
  for an instance
- **THEN** the attempt is refused

### Requirement: Per-instance configuration is validated and passed through unchanged

Fred SHALL render the instance configuration form from the definition's declared
fields, as resolved from its stored declaration, and SHALL do so whether or not
the definition's pod is running. Control Plane SHALL serve those declared fields
per definition to the members of a team the definition is enabled for, and to
nobody else.

Fred SHALL validate submitted values against those declarations before storing
them, using one canonical strict validation applied both when an instance is
created or updated and again before a handler is invoked. Values SHALL NOT be
coerced permissively across types. Fred SHALL NOT interpret the meaning of any
value, and a handler SHALL receive configuration already validated so that it
never re-parses its own configuration. That guarantee SHALL be attributed on the
author-facing surface to the platform-provided runtime that dispatches the run,
and SHALL NOT be presented there as a property the run context carries on its
own. A value declared secret SHALL NOT be returned in any read intended for
display.

#### Scenario: A form is rendered while the pod is stopped

- **WHEN** a team member configures an instance of a definition whose
  declaration was published earlier and whose pod is not currently running
- **THEN** the form is rendered from the stored declaration exactly as it would
  be while the pod runs

#### Scenario: Declared fields are not readable outside an enabled team

- **WHEN** a user who is not a member of a team the definition is enabled for
  requests its declared configuration fields
- **THEN** the request is refused

#### Scenario: Invalid configuration is rejected naming the field

- **WHEN** a user submits a value violating a field's declaration, or omits a
  required field
- **THEN** the submission is rejected and the response identifies the offending
  field

#### Scenario: Values reach the implementation unmodified and secrets are not disclosed

- **WHEN** an instance's configuration is delivered to the implementation at run
  time, and separately read back for display
- **THEN** the implementation receives exactly the values the user supplied, and
  the display read contains no secret-declared value

### Requirement: Runs are dispatched to the definition's own worker

A run SHALL be dispatched using the definition's internal execution routing, so
that it reaches the worker hosting that definition. A run for one definition
SHALL NOT be delivered to a worker hosting a different definition. When no
worker is available, the run SHALL eventually reach a terminal failure according
to the configured execution timeouts rather than being silently dropped.

That routing SHALL be derived from the definition's identity, by one derivation
shared by the dispatching side and the worker side, so that the two can never
disagree. It SHALL NOT be authored, configured or otherwise stated a second time
anywhere. The derivation SHALL be a pure function of the definition's identity
and SHALL be part of the documented contract rather than a private
implementation detail.

#### Scenario: Routing is derived, so definitions cannot receive each other's runs

- **WHEN** two Knowledge Base applications are published, each hosting a
  different definition, and their workers start
- **THEN** each side derives the same routing from the definition's identity with
  no configuration or declaration value able to set it otherwise, and neither
  application receives a run belonging to the other's definition

#### Scenario: Missing worker fails observably, not immediately

- **WHEN** a run is dispatched for a definition whose pod is not running
- **THEN** the run is eventually recorded with a terminal failure state, and no
  failure is reported at enablement or instance-creation time

### Requirement: The author-facing API exposes no scheduling-engine concepts

The published author-facing surface SHALL consist of the declaration and its
configuration-field declarations, one synchronization handler, the context
passed to it, the result returned from it, and the entry points that start the
application — one publishing its declaration, one serving runs. A run entry
point SHALL take the declaration and nothing else, deriving or reading from the
pod's environment everything else it needs. The SDK SHALL define that
environment contract — what the pod reads to reach Control Plane, to
authenticate, and to reach the workflow engine — so that a third party deploys
against a documented contract rather than guessed names. Fred SHALL neither read
nor know that environment. Exported names and public signatures SHALL NOT
contain workflow, activity, task-queue, retry, heartbeat or schedule types or
terminology. Internal dependence on the workflow engine is permitted.

#### Scenario: A complete implementation declares only a handler

- **WHEN** a developer writes a declaration with configuration fields, one
  synchronization handler, and the run entry point
- **THEN** the application serves runs with no further code, its entry point
  needs no argument beyond the declaration, and its handler signature contains no
  retry, heartbeat, cancellation or queue parameter

#### Scenario: Engine plumbing is handled outside the handler and absent from public exports

- **WHEN** a run is retried, cancelled, or must remain observably alive during a
  long synchronization
- **THEN** the platform-provided runtime handles it without the handler
  implementing or declaring it, and the package's public exports contain no
  scheduling-engine type or term

### Requirement: Run context is fetched per run and authorized to the exact client

The dispatched run's input SHALL carry stable identifiers only — at minimum the
definition, instance and team — and SHALL NOT carry the complete instance
configuration or any plaintext secret.

The runtime SHALL obtain the run's configuration through an authenticated call
using its own confidential M2M client. Fred SHALL verify the signature-derived
client identity against the client bound to that definition; a broad service
role alone SHALL NOT authorize the call. A user access token SHALL NOT be used
or propagated. Access SHALL be scoped to an active run, its instance and its
team.

What the handler receives SHALL NOT name any location for the implementation's
own synchronization state, and Fred SHALL NOT provide a state directory or store
for it.

#### Scenario: Durable run history holds identifiers only

- **WHEN** a run's durable execution history is inspected after completion
- **THEN** it contains the definition, instance, team and run identifiers, and
  no configuration values and no secret

#### Scenario: A different definition's client is refused

- **WHEN** a client bound to one definition requests the run context of another
  definition's instance
- **THEN** the request is refused, and holding a broad service role does not
  make it succeed

#### Scenario: No user token is involved

- **WHEN** the runtime authenticates to Fred for run context or result reporting
- **THEN** it uses its own workload identity and no user access token is present

#### Scenario: Fred hands over no place to keep state

- **WHEN** a handler is invoked
- **THEN** nothing in what it receives names a location for its own
  synchronization state, and the platform stores none on its behalf

### Requirement: Documents are written through Knowledge Flow's REST API

A Knowledge Base implementation SHALL NOT receive OpenSearch or object-storage
credentials through the Fred SDK contract. It SHALL ingest and delete documents
through Knowledge Flow's REST API, authenticating with its own workload
identity. Direct infrastructure access SHALL be outside the supported portable
contract.

#### Scenario: Documents reach Fred only through that API

- **WHEN** an implementation ingests or deletes documents during a run
- **THEN** every such operation goes through Knowledge Flow's REST API and none
  reaches storage or the index directly

#### Scenario: Infrastructure credentials are never supplied

- **WHEN** an implementation runs
- **THEN** the SDK contract provides it no OpenSearch or object-storage
  credential, and its source credential is used only against the external source

### Requirement: Runs report a bounded structured result and a terminal state

A run SHALL reach a terminal state — succeeded, failed or cancelled — which
Control Plane records and exposes. A completed run SHALL report a bounded
human-readable summary, generic counters covering discovered, created, updated,
removed and unchanged, bounded structured warnings and errors, and an optional
JSON-safe map of implementation-defined metrics. The result SHALL NOT model
source-specific concepts, and content exceeding the declared bounds SHALL be
truncated rather than stored or transmitted unbounded.

Whenever any free-form content is truncated, the result SHALL carry a serialized
indicator saying so. That indicator SHALL be computed by the platform-provided
runtime and SHALL NOT be settable by the implementation, so a clipped report can
never be presented as a complete one. It SHALL report truncation only when
content was actually clipped: content whose length exactly reaches its bound, or
a number of issues exactly reaching the cap, SHALL NOT be reported as truncated.

A structured warning or error SHALL be able to name what it concerns through an
optional, bounded, implementation-defined subject that the platform does not
parse or resolve. Severity SHALL be carried by whether the issue is reported as a
warning or an error, never by a field on the issue.

#### Scenario: The truncation indicator tracks actual clipping

- **WHEN** a handler returns content over its bound — a summary, an issue message
  or subject, or more issues than the cap allows — and, separately, content
  whose length exactly reaches its bound
- **THEN** the first is recorded truncated to the bounds with its indicator true,
  and the second is recorded unchanged with its indicator false

#### Scenario: The truncation indicator cannot be forced

- **WHEN** an implementation returns a truncated result while also asserting
  that nothing was truncated
- **THEN** the recorded indicator still reads true

#### Scenario: Successful run records counters and passes metrics through

- **WHEN** a handler completes successfully returning counters and
  implementation-defined metrics
- **THEN** the run is recorded as succeeded with its counters and summary
  readable, and the metrics are recorded without Fred interpreting them

#### Scenario: Failure and cancellation are terminal, distinguishable, and never partial success

- **WHEN** one run's handler raises after creating some documents and returning
  an over-long summary, and a different run is cancelled
- **THEN** the first reaches a terminal failed state with its content truncated
  to the declared bounds and its counters not marking it successful, and the
  second reaches a terminal cancelled state distinguishable from failure

### Requirement: Reconciliation completeness is stated, and deletion is never inferred

A run's result SHALL state whether the run observed its source exhaustively and
authoritatively. That statement SHALL be independent of the terminal outcome: a
successful run MAY report an incomplete reconciliation, and that combination
SHALL be a valid bounded pass rather than a degraded state.

The removed counter SHALL report retractions the implementation actually
executed through Knowledge Flow. Fred SHALL NOT delete, retract or expire any
document by interpreting that counter. An absence from a source SHALL justify a
deletion only when the run reported a complete, authoritative inventory; an
explicit tombstone from the source MAY be acted on even during an incomplete
pass.

#### Scenario: A bounded pass succeeds without claiming completeness

- **WHEN** a handler covers only part of its source — a page limit, a filter or
  a budget — and returns successfully
- **THEN** the run is recorded as succeeded with its reconciliation reported
  incomplete, and no document is deleted on the strength of what it did not see

#### Scenario: An executed retraction is reported, not requested

- **WHEN** a run reports retractions it carried out
- **THEN** Fred records the count and performs no deletion of its own as a
  result

### Requirement: Failure is reported or raised, and both end terminally

An implementation SHALL be able to report an expected business failure as a
terminal failed result carrying bounded, sanitized error information. An
exception escaping the handler SHALL be treated as an execution failure that the
platform-provided runtime retries internally, reaching a terminal failed state
once retries are exhausted, again with bounded and sanitized error content.
Neither path SHALL expose a secret or an unbounded payload.

#### Scenario: A reported failure is terminal without being retried as a crash

- **WHEN** a handler returns a failed result
- **THEN** the run is recorded as failed with its bounded error information, and
  the platform does not retry it as though it had crashed

#### Scenario: An escaped exception is retried, then terminal

- **WHEN** a handler raises and its retries are exhausted
- **THEN** the run reaches a terminal failed state carrying bounded, sanitized
  error information
