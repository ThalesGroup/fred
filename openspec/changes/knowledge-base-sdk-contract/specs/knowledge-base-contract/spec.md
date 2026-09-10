## Purpose

Defines how a Knowledge Base definition is declared by an SDK author, configured
into a Fred deployment, made available to a team, instantiated and scheduled by
that team, dispatched to its worker, authorized at run time, and reported on —
so that a domain developer writes only a synchronization handler and a team
controls its own configuration and cadence.

## ADDED Requirements

### Requirement: Configured definitions are validated at startup and are not a liveness signal

Knowledge Base definitions SHALL be installed through the Control Plane
deployment configuration. Control Plane SHALL validate every configured
definition at startup and SHALL refuse to serve an invalid one. A configured
definition SHALL carry enough information to derive or resolve its identity and
version, its display metadata, its instance configuration fields, its expected
dedicated M2M client identity, and its internal execution routing.

Being configured SHALL mean only that the definition is visible to a Platform
Admin, may be enabled for a team, and may be instantiated by an enabled team. It
SHALL NOT imply that a pod exists, that a worker is connected, or that the
Knowledge Base is reachable. Fred SHALL NOT check worker availability, and no
surface SHALL present a configured definition as online.

#### Scenario: Invalid configured definition is refused at startup

- **WHEN** a deployment is configured with a definition missing required
  declaration content
- **THEN** startup validation rejects it and the deployment does not serve it as
  an available definition

#### Scenario: Configured definition is not reported as online

- **WHEN** a Platform Admin views a configured definition whose pod is not
  running
- **THEN** the definition is shown as configured and available, with no claim
  about connectivity, health or worker presence

### Requirement: Platform Admin visibility and team enablement

A configured definition SHALL be visible to a Platform Admin, who alone may
enable it for a team. A definition SHALL NOT be usable by a team until enabled
for that team. Enablement SHALL be an availability decision only and SHALL store
no configuration values. Disabling SHALL prevent creation of new instances for
that team.

#### Scenario: Definition is unusable before enablement

- **WHEN** a definition is configured but not enabled for a team
- **THEN** a member of that team cannot create an instance of it

#### Scenario: Enablement grants availability without storing configuration

- **WHEN** a Platform Admin enables a configured definition for a team
- **THEN** members of that team can create instances of it, and no configuration
  values are recorded by the enablement itself

### Requirement: Team-scoped instances, more than one per definition

A team SHALL be able to create more than one instance of the same enabled
definition, each carrying its own configuration, schedule and run history. Every
instance SHALL belong to exactly one team, and its configuration, schedule and
runs SHALL be accessible only within that team.

#### Scenario: Two instances of one definition coexist

- **WHEN** a team creates two instances of the same definition with different
  configuration values
- **THEN** both exist independently with their own schedules and run histories,
  and neither overwrites the other

#### Scenario: Another team cannot reach an instance

- **WHEN** a user outside the owning team attempts to read, modify or list runs
  for an instance
- **THEN** the attempt is refused

### Requirement: Per-instance configuration is validated and passed through unchanged

Fred SHALL render the instance configuration form from the definition's declared
fields and SHALL validate submitted values against those declarations before
storing them. Fred SHALL NOT interpret the meaning of any value. A value
declared secret SHALL NOT be returned in any read intended for display.

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

### Requirement: Typed daily and weekly schedules with time zone

An instance's schedule SHALL be expressed as a daily or weekly recurrence with a
local time of day and an IANA time zone, and for a weekly recurrence a day of
the week. Raw cron expressions SHALL NOT be accepted or displayed, and no
scheduling-engine terminology SHALL appear in the user-facing schedule. An
instance SHALL be able to carry no recurrence at all.

#### Scenario: Weekly schedule runs at local time across a daylight-saving change

- **WHEN** a user selects "every Thursday at 05:00 Europe/Paris" and the zone
  later crosses a daylight-saving transition
- **THEN** runs occur only on Thursdays and continue to occur at 05:00 local time

#### Scenario: No recurrence is valid and cron is not offered

- **WHEN** a user creates an instance without selecting a recurrence
- **THEN** the instance is valid, is never dispatched on a schedule, and at no
  point is a cron expression accepted or displayed

### Requirement: Schedule lifecycle follows instance lifecycle and prevents overlap

Control Plane SHALL create the recurring schedule when an instance with a
recurrence is created, update it in place when the recurrence changes, suspend
it when the instance is disabled, resume it when re-enabled, and delete it when
the instance is deleted. No schedule SHALL outlive its instance. When a run
becomes due for an instance whose previous run is still active, a second
concurrent run SHALL NOT start; this SHALL be a platform default and SHALL NOT
be offered as a per-instance user choice.

#### Scenario: Recurrence change updates one schedule in place

- **WHEN** a user changes an instance's recurrence
- **THEN** the existing schedule is updated and no second schedule exists for
  that instance

#### Scenario: Disable suspends, re-enable resumes, delete removes

- **WHEN** an instance is disabled, later re-enabled, and later deleted
- **THEN** dispatch stops on disable, resumes on re-enable without the user
  re-entering the recurrence, and the schedule is removed on delete

#### Scenario: A due run is skipped while one is active

- **WHEN** an instance's next occurrence becomes due while its previous run is
  still active
- **THEN** no second concurrent run starts, and the following occurrence runs
  normally once the active run finishes

### Requirement: Runs are dispatched to the definition's own worker

A scheduled run SHALL be dispatched using the configured definition's internal
execution routing, so that it reaches the worker hosting that definition. A run
for one definition SHALL NOT be delivered to a worker hosting a different
definition. When no worker is available, the run SHALL eventually reach a
terminal failure according to the configured execution timeouts rather than
being silently dropped.

#### Scenario: Two definitions do not receive each other's runs

- **WHEN** two Knowledge Base applications are configured, each hosting a
  different definition
- **THEN** neither receives a run belonging to the other's definition

#### Scenario: Missing worker fails observably, not immediately

- **WHEN** a scheduled run fires for a definition whose pod is not running
- **THEN** the run is eventually recorded with a terminal failure state, and no
  failure is reported at enablement or instance-creation time

### Requirement: The author-facing API exposes no scheduling-engine concepts

The published author-facing surface SHALL consist of the declaration and its
configuration-field declarations, one synchronization handler, the context
passed to it, the result returned from it, and a run entry point. Exported names
and public signatures SHALL NOT contain workflow, activity, task-queue, retry,
heartbeat or schedule types or terminology. Internal dependence on the workflow
engine is permitted.

#### Scenario: A complete implementation declares only a handler

- **WHEN** a developer writes a declaration with configuration fields, one
  synchronization handler, and the run entry point
- **THEN** the application serves scheduled runs with no further code, and its
  handler signature contains no retry, heartbeat, cancellation or queue parameter

#### Scenario: Engine plumbing is handled outside the handler and absent from public exports

- **WHEN** a run is retried, cancelled, or must remain observably alive during a
  long synchronization
- **THEN** the platform-provided runtime handles it without the handler
  implementing or declaring it, and the package's public exports contain no
  scheduling-engine type or term

### Requirement: Run context is fetched per run and authorized to the exact client

The dispatched run's input SHALL carry stable identifiers only — at minimum the
definition, instance and team — and SHALL NOT carry the complete instance
configuration or any plaintext secret. A run identifier MAY be derived when the
run starts rather than being a static schedule argument.

The runtime SHALL obtain the run's configuration through an authenticated call
using its own confidential M2M client. Fred SHALL verify the signature-derived
client identity against the definition's configured client; a broad service role
alone SHALL NOT authorize the call. A user access token SHALL NOT be used or
propagated. Access SHALL be scoped to an active run, its instance and its team.

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

### Requirement: Documents are written through a scoped Knowledge Flow boundary

A Knowledge Base implementation SHALL NOT receive OpenSearch or object-storage
credentials through the Fred SDK contract. It SHALL write through a Knowledge
Flow document boundary supporting scoped read, list, upsert and delete. Every
such operation SHALL be restricted to the current team and Knowledge Base
instance, and SHALL validate the exact KB client identity and the active run
binding. Direct infrastructure access SHALL be outside the supported portable
contract.

#### Scenario: Writes are confined to the running instance's scope

- **WHEN** an implementation reads, lists, upserts or deletes documents during a
  run
- **THEN** every operation is confined to the current team and instance, and an
  attempt to reach another instance's documents is refused

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
