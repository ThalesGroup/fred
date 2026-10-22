## ADDED Requirements

### Requirement: On-demand conversation workload
The broker SHALL create no idle sandbox workload before execution. It SHALL create at most one isolated workload for a conversation on its first execution, reuse it until the configured inactivity deadline, and destroy it when the deadline expires. Admin and operator settings SHALL NOT permit a positive preloaded capacity. A SIG Agent Sandbox pool object MAY exist only with zero replicas if required for claims.

#### Scenario: No execution
- **WHEN** users open conversations without executing code
- **THEN** no sandbox Pod, VM or container is created for them

#### Scenario: Repeated execution
- **WHEN** the same conversation executes code again before its inactivity deadline
- **THEN** it reuses its private workload and scratch directory without creating another workload

### Requirement: Conversation sandbox workspace
The system SHALL present authorized agents with a conversation-scoped workspace. `/skills` and `/inputs` SHALL be read-only mounts backed by authorized source views, and `/work` SHALL be writable scratch space in the isolated workload. The system SHALL resolve file reads on demand without pre-copying selected source bytes into guest scratch. It MUST NOT mount arbitrary host paths, the raw corpus store, credentials, or another conversation's files into the workload.

#### Scenario: Shared files within one conversation
- **WHEN** an authorized agent selects a file and runs Python, then runs Python again before the idle deadline
- **THEN** both executions can read the source through the same mounted path and the second can read scratch files created by the first

#### Scenario: Cross-conversation access
- **WHEN** another conversation requests the same virtual path
- **THEN** it cannot read the first conversation's input or scratch bytes

#### Scenario: Invalid source selection
- **WHEN** a requested file is unauthorized, too large, missing, or has an unsafe path
- **THEN** the source is not bound to the conversation mount and no file bytes are returned

#### Scenario: Mount provider unavailable
- **WHEN** the selected isolation backend cannot provide an approved read-only source mount
- **THEN** filesystem-backed sandbox execution fails closed while existing non-sandbox document and skill tools remain available

### Requirement: Unified execution gate
The system SHALL use the existing admin-gated `code_sandbox` capability for every Bash or Python execution path in ReAct and Deep, including native filesystem execution if enabled. Disabling the capability SHALL leave no executable model tool or filesystem operation, while existing skill and document tools keep their current behavior. Scripts from a skill SHALL be treated as untrusted code and use the same backend, isolation profile, resource limits, and conversation identity as agent-written code.

#### Scenario: Disabled capability
- **WHEN** an agent lacks `code_sandbox`
- **THEN** it cannot execute a command through either the code tool or a native filesystem tool
- **AND** it can still load ordinary skills and use its existing authorized document tools

#### Scenario: Skill script
- **WHEN** an authorized agent invokes a published skill script
- **THEN** it runs in the isolated conversation workload with no extra credentials, network access, or host mounts

### Requirement: Bounded mounted file access
The system SHALL enforce per-file, per-conversation, read-volume and path limits at the source-view boundary. It SHALL reject traversal, escaping links, special files, unsupported paths and arbitrary model-provided host paths. The mounted view SHALL be bound to one active conversation lease. The broker SHALL revoke that binding and remove scratch files on expiry or disposal.

#### Scenario: Oversized file
- **WHEN** a selected source exceeds an operator hard limit
- **THEN** the agent receives a bounded error and the mounted view does not expose that file

#### Scenario: Conversation expiry
- **WHEN** the conversation's sandbox lease expires
- **THEN** its mounted source view is revoked and its scratch data is destroyed with the workload
