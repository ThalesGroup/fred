## ADDED Requirements

### Requirement: Task progress is read in batches without long-lived connections

The system SHALL follow the progress of the tasks a user started by periodically
reading their current state, in batches, from the backend that owns them. It
SHALL NOT hold a connection open per task. While at least one followed task is
active, the system SHALL read in rounds: a round reads every followed task from
its owning backend, in batches of at most 50 tasks read one after another, and
the next round starts one polling interval after the previous one ended. At most
one read SHALL be in flight at a time, and reading SHALL stop once no followed
task is active.

#### Scenario: Many files are imported at once

- **WHEN** a user follows more tasks than the browser allows concurrent
  connections to one origin
- **THEN** every task still reaches its outcome
- **AND** the page's other requests are not held back by the following of those
  tasks

#### Scenario: Nothing is left to follow

- **WHEN** every followed task has reached its outcome
- **THEN** the system stops reading task states
- **WHEN** a new task is followed
- **THEN** reading resumes

#### Scenario: The tab comes back to the foreground

- **WHEN** a tab with active tasks becomes visible again
- **THEN** their states are read without waiting for the next interval

### Requirement: Following converges on the recorded outcome

Each followed task SHALL reach the outcome the owning backend recorded for it,
without a page reload, whatever the user did in between: navigating to another
page, leaving the tab in the background, or the access token expiring. A failed
or cancelled outcome SHALL be shown as such, never as succeeded.

#### Scenario: The access token expires during an import

- **WHEN** the access token expires while tasks are being followed
- **AND** the session is still valid
- **THEN** the next read is made with a renewed token and every task reaches its
  recorded outcome

#### Scenario: The user is on another page when a task finishes

- **WHEN** a followed task finishes while the user is on another page
- **THEN** returning to the page that shows it displays its outcome

#### Scenario: A task fails

- **WHEN** the owning backend records a task as failed
- **THEN** the import panel and the document row show it as failed

### Requirement: An outcome is final

Once the system has shown a task's outcome, no later read SHALL change it.

#### Scenario: A read arrives after a newer one

- **WHEN** a task is shown as succeeded, failed or cancelled
- **AND** a read reports it in a non-terminal state
- **THEN** the task keeps the outcome it has

### Requirement: A read that fails changes nothing

A read that fails (network error, server error, owning backend unavailable)
SHALL leave every task as it was and SHALL be retried at the next interval. It
SHALL NOT be interpreted as an outcome.

#### Scenario: A backend is briefly unavailable

- **WHEN** reads to a backend fail for a while, then succeed again
- **THEN** its tasks keep their last known state while it is unavailable
- **AND** then reach their recorded outcome

### Requirement: A task the server no longer knows is shown as untracked

When the owning backend answers a read without a task that was asked for, the
system SHALL mark that task untracked and stop following it. An untracked task
SHALL NOT be shown as succeeded, failed or in progress. The import panel SHALL
say that following stopped and offer to dismiss the entry. The document row
SHALL show the document's own status.

#### Scenario: A followed task is missing from the answer

- **WHEN** a read asks for a task and the owning backend's answer does not
  contain it
- **THEN** the import panel shows that following stopped for that file, with an
  action to dismiss it
- **AND** the document row shows the document's own status rather than
  "Processing…"
- **AND** no further read asks for that task

### Requirement: The task list can be read by id

`GET /tasks?scope=user` on every task-owning backend SHALL accept a repeated
`task_id` parameter of 1 to 50 values. With it, the response SHALL contain the
caller's own tasks among those ids, whatever their state, and no other task.
More than 50 values, or the parameter with another scope, SHALL be rejected with
422. Without the parameter, the response SHALL be unchanged.

#### Scenario: Reading active and finished tasks together

- **WHEN** a user reads their tasks by id, some running and some finished
- **THEN** all of them are returned with their current state

#### Scenario: Asking for someone else's task

- **WHEN** a user's read includes the id of a task they did not start
- **THEN** that task is absent from the response
- **AND** the response does not reveal whether it exists

#### Scenario: Too many ids

- **WHEN** a read includes more than 50 ids
- **THEN** it is rejected with 422
