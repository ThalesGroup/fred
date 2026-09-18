# Deep Agent Todo Panel Specification

## Purpose

Defines how Fred presents a Deep Agent's persisted `write_todos` planning state as a dedicated conversation task panel without duplicating that state or its storage.

## Requirements

### Requirement: The conversation displays the latest valid todo snapshot

The chat SHALL derive its task panel from the latest valid `write_todos` tool call in conversation order that has not received an explicitly failed tool result. A valid snapshot SHALL contain a `todos` array whose items each contain non-empty text and one of the statuses `pending`, `in_progress`, or `completed`.

#### Scenario: A live todo snapshot arrives

- **WHEN** the active conversation receives a valid `write_todos` tool call
- **THEN** the task panel displays that call's complete todo snapshot
- **AND** it replaces any earlier displayed snapshot

#### Scenario: Persisted history is restored

- **WHEN** a conversation containing valid `write_todos` calls is reopened or reloaded
- **THEN** the task panel displays the same latest valid snapshot from the restored conversation history

#### Scenario: An invalid snapshot follows a valid snapshot

- **WHEN** a malformed or unsupported `write_todos` payload appears after a valid snapshot
- **THEN** the malformed payload does not replace the last valid snapshot

#### Scenario: A todo update fails

- **WHEN** a valid `write_todos` call receives an explicitly failed tool result
- **THEN** that call does not replace the last successful snapshot
- **AND** the failed call and result remain available in the generic trace

#### Scenario: The latest valid snapshot is empty

- **WHEN** the latest valid `write_todos` call contains an empty `todos` array
- **THEN** the task panel is not displayed
- **AND** the polite live region announces completion

#### Scenario: The conversation has no valid snapshot

- **WHEN** a conversation contains no valid `write_todos` snapshot
- **THEN** no task panel is displayed

### Requirement: The task panel stays adjacent to the composer

The task panel SHALL appear between the scrollable conversation and the chat composer, SHALL remain outside the conversation's scroll area, and SHALL extend behind the higher-stacking composer. Hover feedback SHALL remain confined to the panel header and MUST NOT tint the backing surface through the composer.

#### Scenario: The user scrolls a conversation with active tasks

- **WHEN** the user scrolls through conversation messages while a task panel is present
- **THEN** the panel remains visible immediately above the composer

### Requirement: The task panel communicates task progress accessibly

The task panel SHALL distinguish pending, in-progress, and completed tasks visually and through accessible semantics. Its header SHALL report the number of tasks whose status is not `completed`, and its expanded view SHALL retain completed tasks.

#### Scenario: A snapshot contains mixed task states

- **WHEN** the current snapshot contains pending, in-progress, and completed tasks
- **THEN** each task is presented with its corresponding state
- **AND** the remaining count includes pending and in-progress tasks only
- **AND** completed tasks remain visible while the panel is expanded

#### Scenario: The active step finishes with the assistant turn

- **WHEN** the same exchange emits a final answer without an error or failed tool result while its latest snapshot still marks a task `in_progress`
- **THEN** the panel presents that task as completed
- **AND** the remaining count excludes that completed step
- **AND** the panel disappears when no pending task remains

#### Scenario: The streamed final retains an earlier message slot

- **WHEN** the streaming reducer replaces a reserved final frame in an array position before later todo tool events from the same exchange
- **THEN** the final answer still settles the exchange's active task
- **AND** settlement does not depend on the final frame appearing after the todo call in array order

#### Scenario: The assistant turn fails

- **WHEN** the exchange emits an error or failed tool result before its final answer
- **THEN** an `in_progress` task remains unfinished
- **AND** the panel does not infer successful completion from that final answer

#### Scenario: Every task is complete

- **WHEN** every task in the current snapshot has status `completed`
- **THEN** the task panel is not displayed

#### Scenario: Task state changes

- **WHEN** tasks are added, change status, change remaining count, or finish completely
- **THEN** a persistent polite live region announces the updated task plan

### Requirement: Panel expansion is persistent per conversation

The task panel SHALL be collapsible and SHALL persist an explicit expanded or collapsed choice separately for each conversation. Without an explicit choice, it SHALL be expanded while work remains. A saved choice MUST NOT keep the panel visible when no work remains.

#### Scenario: The user returns to a conversation

- **WHEN** the user explicitly changes the panel expansion state and later reloads or returns to the same conversation
- **THEN** the panel restores that conversation's saved expansion state

#### Scenario: Another conversation has a task panel

- **WHEN** the user opens a different conversation with its own todo snapshot
- **THEN** the first conversation's expansion choice does not override the second conversation's choice or default

### Requirement: Represented todo calls do not duplicate in the reasoning trace

A valid `write_todos` tool call represented by the task panel and its non-failed matching tool result SHALL be omitted from `ThoughtTrace`. Invalid or explicitly failed `write_todos` calls and unmatched diagnostic messages SHALL remain available in the generic trace.

#### Scenario: A valid todo call has a matching result

- **WHEN** a trace contains a valid `write_todos` call and a tool result with the same call identifier
- **THEN** neither message produces a generic trace row
- **AND** the snapshot is represented by the task panel

#### Scenario: A todo call is malformed

- **WHEN** a trace contains a malformed `write_todos` call
- **THEN** the call remains visible through the generic trace behavior
- **AND** a matching result remains paired with it when present

#### Scenario: A todo call fails

- **WHEN** a valid `write_todos` call has a matching tool result whose status is failed
- **THEN** the call and result remain paired and visible through the generic trace behavior

#### Scenario: Other tools are present

- **WHEN** a trace contains tool calls other than valid `write_todos` calls
- **THEN** their grouping, status, and display behavior remain unchanged

### Requirement: Todo presentation does not create a second source of truth

The task panel SHALL use existing streamed and persisted conversation messages as its only todo-content source. It MUST NOT require a separate todo API, database record, workspace file, or synchronization with `TODO.md`.

#### Scenario: The task panel is introduced

- **WHEN** the feature is deployed
- **THEN** existing conversations and runtimes require no data migration
- **AND** Deep Agents continue to own todo updates through `write_todos`
