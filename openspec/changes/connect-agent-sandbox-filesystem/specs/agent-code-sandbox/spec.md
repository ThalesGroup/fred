## MODIFIED Requirements

### Requirement: Agent code execution tool
The system SHALL expose an admin-gated `execute_code(code)` tool whose sole model-visible argument is a bounded Bash script. Kubernetes, SIG Agent Sandbox and Docker backends SHALL execute it through `/bin/bash -c`; Python and other installed interpreters SHALL be invoked explicitly by the script. The tool SHALL return exit status and bounded stdout and stderr, or an explicit execution error. Unexpected request fields SHALL be rejected before provisioning a workload.

#### Scenario: Python through Bash
- **WHEN** an authorized agent submits `python - <<'PY'` followed by Python source and the closing delimiter
- **THEN** the isolated workload runs the Python program and returns its output and exit status

#### Scenario: Unexpected request field
- **WHEN** a caller sends an extra argument with code
- **THEN** validation rejects the request without creating a workload

## ADDED Requirements

### Requirement: Grouped code execution trace
The chat thought trace SHALL display a consecutive run of `execute_code` calls in one assistant turn as one expandable activity. Its single-line heading SHALL show the command count and only the bounded intent comment of the running command, or the latest command when none is running. It SHALL not show submitted code in the heading. Expanding it SHALL show commands in chronological order with their status and links to full code and result details. The tool guidance SHALL ask the agent to start every execution, including a single Bash command, with a short shell comment describing intent. When present, the leading comment SHALL appear in the heading and as an ordinary intent label in the expanded row, followed there by the submitted code in a visually distinct monospace surface, flattened in source order onto one line; neither SHALL be treated as evidence of what the script actually did. Without a leading comment, the heading SHALL show only the command count. A long preview SHALL be truncated with `...`. It SHALL not parse or classify heredoc syntax. The tool SHALL still execute and retain the submitted code unchanged. Reasoning between consecutive code calls SHALL remain in sequence. A different tool, including `summarize_document`, SHALL end the current activity; a later code call SHALL start a new activity. The grouping mechanism SHALL allow another tool family to opt in through a presentation rule without changing stored trace events.

#### Scenario: Multiple code calls
- **WHEN** an agent executes a Bash command and a Bash script invoking Python consecutively in one turn
- **THEN** the trace shows one code activity with two selectable command previews and their individual details

#### Scenario: Intent comment on a multiline script
- **WHEN** a script starts with `# Search HELIOS-4821 in the attached PDF` before a Python heredoc
- **THEN** the group heading shows that bounded intent without code, and the command row shows the intent followed by the launcher and Python body flattened onto one code-styled line, while the tool detail retains the exact comment, launcher, body and result

#### Scenario: Intent comment on a Bash command
- **WHEN** an agent uses `execute_code` for a single Bash command
- **THEN** the tool guidance asks for a short leading intent comment and the heading shows only that comment, and the expanded row styles the command separately from it

#### Scenario: Unlabeled multiline script
- **WHEN** a script starts with `python - <<'PY'` and has no leading intent comment
- **THEN** the group heading shows no code and the expanded row preview starts with `python - <<'PY'` and continues with its body and closing delimiter in source order on one line, up to the preview limit

#### Scenario: Other tool between code calls
- **WHEN** an agent executes code, calls `summarize_document`, and executes code again
- **THEN** the trace shows a code activity, the ordinary summary tool step, and a separate code activity in that order

#### Scenario: Tool represented outside the trace
- **WHEN** an agent executes code, calls `write_todos` whose plan is shown elsewhere, and executes code again
- **THEN** the trace still shows two separate code activities

#### Scenario: Cancelled execution
- **WHEN** a user cancels approval of a code call in an expanded activity
- **THEN** that command is shown as cancelled rather than failed

#### Scenario: Command exits unsuccessfully
- **WHEN** a Bash script exits with a nonzero status or times out
- **THEN** its trace row and activity are marked as failed while its exit status and bounded output remain available in the detail

#### Scenario: Streaming update
- **WHEN** another code call arrives while a code activity is already displayed
- **THEN** its command appears in that activity without changing the identity or selected detail of earlier calls

### Requirement: On-demand conversation workload
The broker SHALL create no idle sandbox workload before execution. It SHALL create at most one isolated workload for a conversation on its first execution, reuse it until the configured inactivity deadline, and destroy it when the deadline expires. Admin and operator settings SHALL NOT permit a positive preloaded capacity. A SIG Agent Sandbox pool object MAY exist only with zero replicas if required for claims.

#### Scenario: No execution
- **WHEN** users open conversations without executing code
- **THEN** no sandbox Pod, VM or container is created for them

#### Scenario: Repeated execution
- **WHEN** the same conversation executes code again before its inactivity deadline
- **THEN** it reuses its private workload and scratch directory without creating another workload

### Requirement: Conversation sandbox workspace
The system SHALL present authorized agents with a conversation-scoped workspace. `/skills`, `/inputs/corpus` and `/inputs/attachments` SHALL be read-only mounts backed by authorized source views, and `/work` SHALL be writable scratch space in the isolated workload. The corpus directory SHALL enumerate readable documents in pages beneath libraries owned by the conversation's team or personal user; the attachment directory SHALL enumerate retained originals belonging to that conversation and user. No model tool call SHALL be required to select files before execution. The system SHALL resolve file reads on demand without pre-copying source bytes into guest scratch. It MUST NOT mount arbitrary host paths, the raw corpus store, credentials, or another conversation's files into the workload. File mounts SHALL fail closed when ReBAC is disabled.

#### Scenario: Shared files within one conversation
- **WHEN** an authorized agent reads a mounted file and runs Python again before the idle deadline
- **THEN** both executions can read the source through the same mounted path and the second can read scratch files created by the first

#### Scenario: Parallel code calls in one conversation
- **WHEN** the agent issues concurrent code calls before the conversation's file view exists
- **THEN** each call may open the same authorized view without a duplicate-key failure, and the view remains bound to that conversation's user and team

#### Scenario: Shared approved skill source
- **WHEN** the runtime `/` catalog and sandbox profile use the same approved skill source
- **THEN** its skills and scripts are mounted read-only under `/skills` in the guest without copying them into its scratch or another publication store
- **AND** a newly added source skill becomes visible in the guest after the directory cache refresh

#### Scenario: Cross-conversation access
- **WHEN** another conversation requests the same virtual path
- **THEN** it cannot read the first conversation's input or scratch bytes

#### Scenario: Unauthorized or invalid source
- **WHEN** a file is unauthorized, too large, missing, or has an unsafe path
- **THEN** it is absent from the directory listing and no file bytes are returned

#### Scenario: New file during a conversation
- **WHEN** an authorized document or attachment is added after the sandbox starts
- **THEN** it becomes visible through the read-only view without recreating the workload

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
- **WHEN** a source exceeds an operator hard limit
- **THEN** the agent receives a bounded error and the mounted view does not expose that file

#### Scenario: Conversation expiry
- **WHEN** the conversation's sandbox lease expires
- **THEN** its mounted source view is revoked and its scratch data is destroyed with the workload
