# Deep conversation filesystem Specification

## Purpose

Defines the conversation-scoped filesystem that lets a Deep agent, its native subagents, and trusted runtime capabilities exchange durable working files without exposing data from another conversation.

## Requirements

### Requirement: Every Deep conversation has a standard scratchpad

The runtime SHALL provide every Deep agent conversation with a text-only `/` namespace without requiring the operator to select or configure a filesystem capability. The model SHALL have `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` operations for that namespace. The filesystem SHALL NOT make code execution available.

#### Scenario: Deep agent uses the scratchpad without an optional capability

- **GIVEN** a Deep agent with no filesystem capability selected
- **WHEN** the agent writes text to `/notes.md` and reads it back
- **THEN** the write and read succeed
- **AND** the `execute` operation remains unavailable

#### Scenario: Binary scratchpad content is rejected

- **WHEN** a caller attempts to store binary content in `/`
- **THEN** the operation fails with an explicit unsupported-content error
- **AND** no partial file is stored

### Requirement: Parent and native subagents share live scratchpad state

The parent Deep agent and every native subagent in the same conversation SHALL access the same `/` namespace. A successful mutation SHALL be visible to subsequent operations without waiting for child completion or state merging.

#### Scenario: Parent reads a child file while work continues

- **GIVEN** a native subagent successfully writes `/research.md`
- **WHEN** the parent reads that path after the write completes
- **THEN** the parent receives the stored content even if the child task has not otherwise completed

#### Scenario: Sibling reads another child's file

- **GIVEN** two native subagents belong to the same conversation
- **AND** one subagent successfully writes a scratchpad file
- **WHEN** the other subagent reads that path after the write completes
- **THEN** it receives the stored content

### Requirement: Scratchpad state persists for the conversation lifetime

Successful scratchpad writes SHALL remain available across later turns and runtime replicas for the same conversation until the conversation becomes eligible for erasure. The runtime SHALL NOT silently fall back to replica-local or checkpoint-only storage when shared storage is unavailable.

#### Scenario: Later turn runs on another replica

- **GIVEN** one turn successfully writes a scratchpad file
- **WHEN** a later turn for the same conversation is served by another runtime replica
- **THEN** the later turn reads the same file content

#### Scenario: Shared storage is unavailable

- **WHEN** a scratchpad operation cannot reach shared storage
- **THEN** the operation fails explicitly
- **AND** the runtime does not report success from a divergent local copy

### Requirement: Conversation files are isolated by conversation identity

The runtime SHALL scope stored files by the globally unique conversation identifier. A caller bound to one conversation SHALL NOT read, list, mutate, or delete files belonging to another conversation, and filesystem paths SHALL NOT escape the bound conversation namespace.

#### Scenario: Same path exists in two conversations

- **GIVEN** two conversations each contain `/notes.md` with different content
- **WHEN** each conversation reads that virtual path
- **THEN** each receives only its own content

#### Scenario: Path traversal is attempted

- **WHEN** a caller supplies a path that would escape its bound conversation namespace
- **THEN** the operation is rejected before accessing storage

### Requirement: Virtual namespaces have distinct permissions

The composite filesystem SHALL route `/` and `/.deep/` to separately scoped areas of the same conversation storage with `/` as the default working namespace. Unsafe paths SHALL be rejected before storage access. Model-originated operations SHALL be permitted to read, list, glob, and grep `/.deep/` but SHALL NOT write or edit it. Trusted Deep runtime internals SHALL be able to write their own `/.deep/` artifacts. Capability callers using agent origin SHALL obey the same effective read/write rules as model tools; system origin SHALL be reserved for trusted runtime operations.

#### Scenario: Model attempts to modify a Deep internal artifact

- **WHEN** the model calls `write_file` or `edit_file` with a path under `/.deep/`
- **THEN** the call fails with a read-only-namespace error
- **AND** the stored artifact remains unchanged

#### Scenario: Deep middleware stores an internal artifact

- **WHEN** trusted Deep runtime middleware persists a large tool result or conversation-history artifact under `/.deep/`
- **THEN** the artifact is stored in the current conversation's internal namespace

### Requirement: Trusted capabilities use the conversation filesystem port

Trusted runtime and capability code SHALL receive `RuntimeServices.conversation_filesystem` as a typed, conversation-bound `ConversationFilesystemPort`. Its async operations SHALL support text read, create/full replacement, expected-text edit, listing and existence checks at safe absolute virtual paths, with explicit `origin="agent"` or `origin="system"`. Agent origin SHALL enforce effective filesystem rules; system origin SHALL be reserved for trusted runtime work. `is_editable(path)` SHALL report effective agent write policy without mutation and SHALL default to false for unknown adapters. The SDK port SHALL NOT expose deletion, credentials, physical storage keys or caller-selected conversation identity. Lower-level runtime deletion and erasure remain available through their owning service.

#### Scenario: Capability writes a file for the agent

- **GIVEN** trusted capability code executing for a conversation
- **WHEN** it writes `/notes.md` through the conversation filesystem port with agent origin
- **THEN** the file becomes visible at `/notes.md` to the parent and native subagents

#### Scenario: Capability uses agent permissions for internal artifacts

- **WHEN** capability code attempts to write `/.deep/history.md` with agent origin
- **THEN** the service rejects the write
- **AND** permitted reads of internal artifacts remain available

#### Scenario: Capability supplies an unsafe path

- **WHEN** capability code supplies a relative or traversing virtual path
- **THEN** the service rejects the operation before accessing storage

### Requirement: Mutations have explicit conflict semantics

Creating a file at an absent path SHALL succeed. An edit SHALL apply to the latest stored text only when its expected old text matches according to the edit operation's contract; otherwise it SHALL fail without changing the file. An explicit full-file replacement SHALL use last-successful-write-wins semantics.

#### Scenario: Edit detects changed content

- **GIVEN** a caller prepared an edit against earlier file content
- **AND** the expected old text no longer matches the latest stored file
- **WHEN** the caller submits the edit
- **THEN** the edit fails
- **AND** the latest stored content is preserved

#### Scenario: Concurrent full replacements complete

- **WHEN** concurrent callers explicitly replace the same complete file
- **THEN** the content from the last successful write is retained
- **AND** neither caller is told that content was merged

### Requirement: Each namespace has a soft safety quota

The runtime SHALL enforce independent total-byte and file-count safety quotas for `/` and `/.deep/`. It SHALL provide safe defaults for all four limits and SHALL allow a deployment to override those defaults through runtime configuration without rebuilding the runtime image. A mutation observed to exceed its namespace quota SHALL fail before storing content. There SHALL be no separate per-file quota. The quota model SHALL permit temporary overshoot during concurrent mutations from multiple runtime replicas, SHALL serialize mutations within one runtime process, and SHALL converge from the actual stored totals when a replica establishes its accounting state.

#### Scenario: Deployment uses default quotas

- **GIVEN** a deployment does not override conversation-filesystem quotas
- **WHEN** Fred Runtime starts
- **THEN** it uses the built-in byte and file-count defaults for both namespaces

#### Scenario: Deployment overrides a quota

- **GIVEN** a deployment supplies a valid conversation-filesystem quota override through runtime configuration
- **WHEN** Fred Runtime starts without rebuilding its image
- **THEN** the configured value replaces the corresponding built-in default
- **AND** unspecified quota values retain their built-in defaults

#### Scenario: Scratchpad mutation exceeds observed byte quota

- **GIVEN** the current scratchpad contents and proposed mutation exceed the scratchpad byte quota
- **WHEN** the mutation is attempted
- **THEN** it fails with an explicit quota error
- **AND** existing files remain unchanged

#### Scenario: One large file fits the namespace quota

- **GIVEN** a single text file fits within the remaining scratchpad byte quota and file-count quota
- **WHEN** the file is written
- **THEN** the write is not rejected merely because the content is held in one file

#### Scenario: Concurrent replicas approve from the same observed total

- **GIVEN** two replicas concurrently calculate sufficient remaining quota from the same stored state
- **WHEN** both mutations succeed
- **THEN** a temporary aggregate overshoot is permitted
- **AND** later accounting uses the actual stored file count and byte total

### Requirement: Conversation erasure includes filesystem data

When an expired or explicitly erased conversation is purged through the standard conversation-erasure flow, the runtime SHALL delete both its scratchpad and Deep internal namespaces before conversation metadata is removed. Cleanup SHALL be idempotent and retryable with the same ownership and runtime-resolution rules as checkpoint and history cleanup.

#### Scenario: Recovery window expires

- **GIVEN** a deleted conversation has reached the end of its recovery window
- **WHEN** the standard erasure flow runs
- **THEN** all stored objects under that conversation's scratchpad and Deep internal namespaces are deleted

#### Scenario: Filesystem cleanup partially fails

- **WHEN** conversation erasure cannot delete one or both filesystem namespaces
- **THEN** the failure is reported as part of the erasure result
- **AND** conversation metadata is retained so a retry can resolve the owning runtime and converge

#### Scenario: Erasure is retried

- **GIVEN** some or all conversation filesystem objects were already deleted
- **WHEN** the erasure flow retries
- **THEN** missing objects are treated as already erased
- **AND** remaining objects are deleted
