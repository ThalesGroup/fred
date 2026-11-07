## Purpose

Allow a configured Fred agent to execute short Bash or Python programs in an isolated, disposable environment through a backend-neutral contract.

## ADDED Requirements

### Requirement: Agent code execution tool
The system SHALL offer an admin-gated agent capability that accepts only a language (`bash` or `python`) and source code from the model. The tool SHALL return exit status and bounded stdout and stderr, or an explicit execution error.

#### Scenario: Python execution succeeds
- **WHEN** an authorized agent calls the tool with Python source that exits successfully
- **THEN** the tool returns the program output and exit status zero

#### Scenario: Unsupported language
- **WHEN** the model requests a language other than Bash or Python
- **THEN** the tool rejects the request before creating a sandbox

### Requirement: Isolation is explicit and mandatory
The system MUST run every sandbox workload with an operator-selected, non-default isolation runtime. It MUST reject execution when the configured runtime is missing, unsupported, or unverifiable and MUST NOT fall back to the host process or default OCI runtime.

#### Scenario: Runtime is unavailable
- **WHEN** the selected runtime cannot be resolved on the target Kubernetes cluster or Docker daemon
- **THEN** the broker rejects the request without starting a workload

### Requirement: Least-privilege execution
The system SHALL execute untrusted code without the agent's credentials, Kubernetes service account token, Docker socket, host mounts, or network access. It SHALL impose finite time, memory, CPU, process, scratch-storage, source-size, and output limits.

#### Scenario: Execution exceeds time limit
- **WHEN** a program runs longer than the configured deadline
- **THEN** the broker stops it, returns a timeout result, and removes its execution resources

#### Scenario: Output exceeds limit
- **WHEN** a program produces output beyond the configured limit
- **THEN** the returned output is truncated and marked as truncated

### Requirement: Backend portability and capacity
The system SHALL expose the same request and result contract through Kubernetes and Docker backends. The broker SHALL bound in-flight executions and reject excess requests before provisioning a workload.

#### Scenario: Capacity is exhausted
- **WHEN** the broker has reached its configured in-flight limit
- **THEN** it rejects the next request with a retryable capacity error and creates no workload

#### Scenario: Backend swap
- **WHEN** an operator switches the configured backend from Docker to Kubernetes with an available approved isolation runtime
- **THEN** the agent tool preserves its arguments and result contract

#### Scenario: SIG Agent Sandbox backend
- **WHEN** the operator selects SIG Agent Sandbox with a matching SandboxTemplate and SandboxWarmPool
- **THEN** the broker creates a SandboxClaim, executes through the same agent contract, and removes the claim and its workload when its conversation lease ends

#### Scenario: Template or pool mismatch
- **WHEN** the upstream template or pool does not match the configured image, runtime or deny-all network boundary
- **THEN** the broker refuses to start

### Requirement: Fast first execution with optional prewarming
The broker SHALL support on-demand provisioning with zero idle sandbox Pods and an optional configurable pool of already running, unassigned sandboxes. A sandbox SHALL be assigned to at most one conversation identity, and SHALL be destroyed after that conversation's idle lease ends; the broker SHALL replenish configured unassigned warm capacity without waiting for the next request. Calls without a conversation identity SHALL remain single-use.

For a trivial program in the selected operating mode, the operator SHALL measure p50 and p95 broker request-to-result latency on the target deployment and use those measurements to choose cold or warm capacity.

#### Scenario: Zero idle mode
- **WHEN** an execution arrives with warm capacity set to zero and available capacity under the hard cap
- **THEN** the broker provisions a new isolated workload for that invocation

#### Scenario: Ready sandbox is available
- **WHEN** an execution arrives while an unassigned sandbox is ready
- **THEN** the broker starts the code in that sandbox without waiting for a new workload to be provisioned

#### Scenario: Warm pool is depleted
- **WHEN** no unassigned sandbox is ready and cold provisioning is disabled
- **THEN** the broker returns a retryable capacity error without reusing another tenant's sandbox

#### Scenario: Latency measurement
- **WHEN** an operator runs the benchmark for the selected cold or ready mode on the target cluster with a trivial program
- **THEN** the benchmark reports p50 and p95 latency for that mode without imposing an arbitrary threshold

### Requirement: Resource cleanup
The broker SHALL attempt to remove a one-shot workload after success, failure, timeout, and request-task cancellation. A conversation workload SHALL be removed after its idle deadline or an unrecoverable execution error. A disconnected client MAY continue to consume capacity only until the configured execution deadline. Kubernetes workloads SHALL additionally have a server-side expiry as a backstop.

#### Scenario: Request task is cancelled
- **WHEN** the broker request task is cancelled after workload creation
- **THEN** the broker attempts to stop and remove that workload

### Requirement: Conversation-scoped execution
The system SHALL privately bind executions to user, team and conversation identity without adding identity to the model-visible tool schema. It SHALL serialize executions in the same conversation, retain scratch files between them, and never share a claimed workload with another conversation or user. The default inactivity expiry SHALL be 20 minutes after the last execution.

#### Scenario: Reuse within a conversation
- **WHEN** the same authorized conversation executes code again before its idle deadline
- **THEN** the broker executes in the same isolated workload and can read scratch files written earlier

#### Scenario: Isolation between conversations
- **WHEN** a different conversation or user executes code
- **THEN** the broker assigns a different workload and cannot read the first conversation's scratch files

#### Scenario: Idle expiry
- **WHEN** no execution occurs in a conversation for the configured idle period
- **THEN** the workload and its scratch files are removed and the next execution starts a fresh workload

### Requirement: Narrow admin settings
The system SHALL allow platform admins to change the idle period, active conversation ceiling, and unassigned warm capacity without redeploy. Operator hard limits SHALL take precedence. The admin interface SHALL show the approved isolation profile and SHALL NOT accept arbitrary image, runtime or security-policy values.

#### Scenario: Admin updates idle expiry
- **WHEN** a platform admin saves a new permitted idle period
- **THEN** the broker applies it within the documented refresh interval and future idle expiry uses the new value

#### Scenario: Unapproved runtime change
- **WHEN** a client attempts to submit an image or runtime through admin settings
- **THEN** the request is rejected and the operator-approved runtime remains in use
