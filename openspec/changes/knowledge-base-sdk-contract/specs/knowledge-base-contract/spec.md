## Purpose

Defines how a Knowledge Base definition is declared by an SDK author, published
into a Fred deployment by its own image, made available to a team, instantiated
and configured by that team, dispatched to its worker, authorized at run time,
and reported on — so that a domain developer writes only a synchronization
handler and a team controls its own configuration.

## ADDED Requirements

### Requirement: A run's state comes from the platform, its report from its author

A run SHALL reach a terminal state — succeeded, failed or cancelled — which
Control Plane records and exposes. That state SHALL be derived from the platform's
own execution record and SHALL NOT depend on the implementation reporting it, so a
run whose pod stopped without reporting still reaches a correct terminal state
rather than appearing unfinished.

A run MAY additionally carry a **report**: content the implementation chose to
show, described by the implementation using the same `FieldSpec` vocabulary that
describes instance configuration. Fred SHALL render that report without
interpreting it, and SHALL NOT require it — a handler returning nothing SHALL be
valid. The platform SHALL NOT impose a vocabulary of its own on that report, and
in particular SHALL NOT require counts of documents discovered, created, updated,
removed or unchanged: an implementation that maintains something other than a
document collection has no such quantities to state.

The report SHALL be self-describing rather than free text or opaque JSON, so that
it can be displayed well by a platform that does not understand it. Content
exceeding the declared bounds SHALL be truncated rather than stored or
transmitted unbounded.

This report SHALL travel the platform's shared background-task surface rather than
a reporting surface specific to Knowledge Bases, since reporting what a background
job did is not particular to them.

Whenever any free-form content is truncated, the result SHALL carry a serialized
indicator saying so. That indicator SHALL be computed by the platform-provided
runtime and SHALL NOT be settable by the implementation, so a clipped report can
never be presented as a complete one. It SHALL report truncation only when
content was actually clipped: content whose length exactly reaches its bound, or
a number of issues exactly reaching the cap, SHALL NOT be reported as truncated.

Bounded warnings and errors SHALL remain part of the contract, unlike the domain
counts removed from it: a severity is not a source's vocabulary but every job's,
and the shared task surface already carries an error of its own. A structured
warning or error SHALL be able to name what it concerns through an optional,
bounded, implementation-defined subject that the platform does not parse or
resolve. Severity SHALL be carried by whether the issue is reported as a warning
or an error, never by a field on the issue.

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

#### Scenario: A run's report is rendered without being understood

- **WHEN** a handler completes successfully describing a report in its own terms —
  a measure it named itself, over a quantity Fred has no concept of
- **THEN** the run is recorded as succeeded and the report is rendered from its own
  description, without Fred interpreting or aggregating it

#### Scenario: A handler that reports nothing is still a complete run

- **WHEN** a handler completes successfully and returns no report at all
- **THEN** the run is recorded as succeeded and displays its state, with no report
  section and no error

#### Scenario: State survives a pod that never reported

- **WHEN** a run's pod stops without reporting anything
- **THEN** the run still reaches a terminal state derived from the platform's
  execution record, rather than remaining indefinitely in progress

#### Scenario: Failure and cancellation are terminal, distinguishable, and never partial success

- **WHEN** one run's handler raises after creating some documents and describing
  an over-long report, and a different run is cancelled
- **THEN** the first reaches a terminal failed state with its content truncated
  to the declared bounds and not presented as successful, and the
  second reaches a terminal cancelled state distinguishable from failure

### Requirement: Deletion is never inferred from a run

Fred SHALL NOT delete, retract or expire any document as a consequence of a run —
neither from what the run reported nor from what it did not report. Retractions
SHALL be actions the implementation carries out itself through Knowledge Flow's
REST API.

Whether an absence from a source justifies a retraction SHALL therefore be the
implementation's decision alone, made against its own ledger. An implementation
that covers only part of its source in one pass SHALL be able to do so without
that pass being treated as degraded, and without any deletion following from it.

*This requirement grew simpler, not weaker: with the platform no longer imposing a
result vocabulary, there is no completeness flag for Fred to act on, and so no
path by which a misreported inventory could cause data loss.*

#### Scenario: A bounded pass is an ordinary success

- **WHEN** a handler covers only part of its source — a page limit, a filter or
  a budget — and returns successfully
- **THEN** the run is recorded as succeeded, and no document is deleted on the
  strength of what it did not see

#### Scenario: A retraction is executed by the implementation, never by Fred

- **WHEN** an implementation retracts documents during a run
- **THEN** those retractions happened through Knowledge Flow's REST API, and Fred
  performs no deletion of its own as a result

### Requirement: Creating a synchronized folder is what authorizes its pod to fill it

A team SHALL create a Knowledge Base instance by creating a folder and naming
the definition that synchronizes it, not through a separate Knowledge Base
surface. Where no definition is enabled for that team, folder creation SHALL be
unchanged.

That creation SHALL, as one transaction, create the library owned by the team,
record the instance against it, grant the definition's publishing identity the
permission to write into that library, and register the instance's cadence. If
any part fails, none SHALL take effect: a library its pod cannot write to is
useless, and a grant over no library is a standing right with no purpose.

The grant SHALL be scoped to that one library. A pod SHALL be able to write into
the libraries of its own instances and SHALL be refused on every other library,
including another instance's within the same team. Authorization to reach Fred
at all SHALL remain separate from, and insufficient for, writing into any
library.

Deleting the folder SHALL undo all of it and SHALL take its documents with it.

#### Scenario: Creating the folder is what makes the pod able to fill it

- **WHEN** a team member creates a folder synchronized by a definition enabled
  for that team, and a run is then dispatched
- **THEN** the library exists, the instance records it, and the pod writes into
  it with its own identity without any further grant being made by hand

#### Scenario: A partial creation leaves nothing behind

- **WHEN** any step of that creation fails
- **THEN** no library, no instance, no grant and no cadence remain

#### Scenario: A pod cannot write outside its own instances

- **WHEN** a pod attempts to write into a library belonging to another instance,
  including one in the same team
- **THEN** the write is refused

#### Scenario: Deleting the folder takes the documents and the grant

- **WHEN** a team member deletes a synchronized folder
- **THEN** its documents are gone, its instance and cadence are gone, and no
  authorization over the deleted library remains

### Requirement: A synchronized folder carries a tree, reached by one grant

A Knowledge Base SHALL be able to reproduce the structure of its source, not
only a flat set of documents. Writing anywhere beneath an instance's library
SHALL require no grant beyond the one made when the folder was created, since
permission over a folder SHALL reach the folders inside it.

An implementation SHALL express where a document goes as a path relative to its
library, and SHALL never be required to know how folders are stored. Folders
missing along that path SHALL be created as part of delivering the document.

Creating a folder inside another SHALL be authorized by permission to write in
that parent. Creating a top-level folder SHALL keep requiring the team-level
right, so that being able to fill one folder never becomes being able to add
folders to a team.

A path that would leave the instance's library SHALL be refused.

#### Scenario: A nested source path creates the folders it needs

- **WHEN** a run delivers a document at a path two folders deep in its library,
  one of which already exists
- **THEN** only the missing folder is created, the document lands in the deepest
  one, and no grant beyond the library's was required

#### Scenario: Writing in a folder does not confer adding folders to the team

- **WHEN** a subject holding only permission to write in one folder creates a
  folder inside it, and separately attempts to create a top-level folder
- **THEN** the first succeeds and the second is refused

#### Scenario: A path cannot escape its library

- **WHEN** a run delivers a document at a path that would place it outside its
  instance's library
- **THEN** the delivery is refused and no folder is created

### Requirement: A publication records the identity that can later be granted

A publication SHALL record both the client the prefix is bound to and the
subject that client authenticates as, since only the second is something the
authorization engine can be told to grant. Both SHALL come from the token that
authorized the publication, so that no directory lookup is needed to grant a
pod access to a library it is later given.

#### Scenario: Publication records what a later grant will need

- **WHEN** a definition is published, and the same publication is replayed on a
  later deployment
- **THEN** the client and its subject are both recorded, replaying leaves them
  unchanged, and a publication presenting a different client is still refused

## MODIFIED Requirements

### Requirement: Per-instance configuration is validated and passed through unchanged

Fred SHALL render the instance configuration form from the definition's declared
fields, as resolved from its stored declaration, and SHALL do so whether or not
the definition's pod is running. Control Plane SHALL serve those declared fields
per definition to the members of a team the definition is enabled for, and to
nobody else.

That form SHALL have two distinguishable zones. A **schedule** zone, declared by
the platform rather than by each author, stating when the instance runs — which
Fred understands and acts upon. And the **author's own declared fields**, which
Fred stores, hands back to the pod at invocation, and never interprets. An author
SHALL NOT need to declare anything to obtain the schedule zone, and an
author-declared field SHALL NOT be able to collide with it.

The schedule zone SHALL stay narrow — a cadence and the ability to suspend it.
Time zones, overlap policy and calendar recurrence beyond that are out of scope,
because a scheduling surface reaches the user, the database and the workflow
engine at once and is expensive to have got wrong.

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

### Requirement: Failure is reported or raised, and both end terminally

An implementation SHALL be able to signal an expected business failure as
terminal without being retried, carrying bounded, sanitized error information. An
exception escaping the handler SHALL be treated as an execution failure that the
platform-provided runtime retries internally, reaching a terminal failed state
once retries are exhausted, again with bounded and sanitized error content.
Retries SHALL be bounded, so that exhaustion is reachable and a deterministically
failing handler terminates rather than retrying indefinitely. Neither path SHALL
expose a secret or an unbounded payload.

#### Scenario: A reported failure is terminal without being retried as a crash

- **WHEN** a handler signals an expected business failure
- **THEN** the run is recorded as failed with its bounded error information, and
  the platform does not retry it as though it had crashed

#### Scenario: An escaped exception is retried, then terminal

- **WHEN** a handler raises and its retries are exhausted
- **THEN** the run reaches a terminal failed state carrying bounded, sanitized
  error information

## REMOVED Requirements

### Requirement: Runs report a bounded structured result and a terminal state

**Reason**: the platform no longer imposes a result vocabulary on an implementation. Replaced by the two requirements added above.

### Requirement: Reconciliation completeness is stated, and deletion is never inferred

**Reason**: the platform no longer imposes a result vocabulary on an implementation. Replaced by the two requirements added above.

