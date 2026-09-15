## Purpose

Defines how a background job reports what it did, so that a job contributed from
outside this repository — a Knowledge Base pod today, anything else tomorrow —
can say something useful in its own vocabulary, and the platform can display it
well without understanding it.

The platform already carries everything generic a background job needs: state,
sequence, timestamp, progress, step, error, target and owner. Only the detail
payload is closed, every arm of it being a type written inside the platform, so a
contributor has no lane. This change opens exactly one.

## ADDED Requirements

### Requirement: A contributed job can report in its own vocabulary

A background job whose code the platform does not own SHALL be able to attach a
report to its task without a type being added to the platform for it. That report
SHALL be optional: a job that reports nothing SHALL remain a complete, correctly
displayed task.

The platform SHALL NOT impose a domain vocabulary on such a report. A job that
maintains a graph, a mailbox or anything that is not a document collection SHALL
NOT be required to state counts that do not apply to it.

#### Scenario: A report the platform has no type for survives intact

- **WHEN** a contributed job reports a measure it named itself, over a quantity
  the platform has no concept of
- **THEN** the report is carried and displayed unchanged, without the platform
  needing a type for it

#### Scenario: Reporting nothing is valid

- **WHEN** a contributed job completes and attaches no report
- **THEN** its task is displayed normally, with its state, and no error

### Requirement: The report describes its own shape

A report SHALL be self-describing, declaring its own fields with the same
`FieldSpec` vocabulary the platform already uses for configuration a contributor
declares. Free text and opaque JSON SHALL NOT be the contract, because neither
can be rendered well by a platform that does not understand it.

The platform SHALL render a report from that description alone, and SHALL NOT
read, aggregate, search or act upon its values.

#### Scenario: The renderer draws a report it cannot interpret

- **WHEN** a task carries a self-described report
- **THEN** each declared field is rendered according to its declared type, and no
  platform behaviour changes as a consequence of any value in it

### Requirement: Opening the lane leaves the platform's own task details unchanged

The typed details the platform writes for its own jobs SHALL be unaffected. For a
job the platform owns, a precise type remains preferable to a generic shape; the
open lane exists for jobs the platform does not own.

A consumer that does not recognise a task's kind SHALL continue to fall back to a
generic presentation rather than failing.

#### Scenario: Existing typed details keep their shape

- **WHEN** the platform's own jobs emit their task details
- **THEN** those details are carried and displayed exactly as before the lane was
  opened

### Requirement: A contributed report is bounded and its truncation is observable

A report SHALL be bounded in size, and content exceeding its bounds SHALL be
truncated rather than carried unbounded — an unbounded report is how a task event
becomes a payload incident.

Whenever content is clipped, the report SHALL carry an indicator saying so, and
that indicator SHALL be computed by the platform rather than set by the reporting
job, so a clipped report can never be presented as complete.

#### Scenario: An oversized report is truncated and says so

- **WHEN** a contributed job reports content beyond the declared bounds and
  asserts that nothing was truncated
- **THEN** the content is stored truncated and the indicator reads true

### Requirement: A contributed job emits only against its own work

A job SHALL be authorized to emit task events only for work it was itself
dispatched to do. Holding a broad service role SHALL NOT on its own authorize
emitting against another contributor's tasks.

#### Scenario: A job cannot report against another's work

- **WHEN** a contributed job attempts to emit a task event for work dispatched to
  a different contributor
- **THEN** the attempt is refused
