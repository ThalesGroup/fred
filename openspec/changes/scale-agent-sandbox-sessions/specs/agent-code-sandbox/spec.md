## MODIFIED Requirements

### Requirement: Backend portability and capacity
The system SHALL expose the same request and result contract through Kubernetes and Docker backends. The broker SHALL bound active sandboxes globally when configured with a shared coordinator. At capacity it SHALL wait for at most an operator-bounded interval, without provisioning an extra workload, then return a retryable capacity error. Admission SHALL prevent one tenant from monopolizing the bounded waiting room. Local single-broker Docker mode MAY reject immediately.

#### Scenario: Capacity is exhausted
- **WHEN** all approved active slots are occupied and the waiting interval expires
- **THEN** the broker returns a retryable capacity error and creates no workload

#### Scenario: Slot becomes free
- **WHEN** a slot is released before an admitted request's waiting deadline
- **THEN** the request can provision its own isolated workload without exceeding the global cap

#### Scenario: Concurrent broker replicas
- **WHEN** two broker replicas receive first executions for different conversations at the last available slot
- **THEN** at most one workload is admitted and the other request waits or receives the capacity error

#### Scenario: Backend swap
- **WHEN** an operator switches the configured backend from Docker to Kubernetes with an available approved isolation runtime
- **THEN** the agent tool preserves its arguments and result contract

#### Scenario: SIG Agent Sandbox backend
- **WHEN** the operator selects SIG Agent Sandbox with a matching SandboxTemplate and SandboxWarmPool
- **THEN** the broker creates a SandboxClaim, executes through the same agent contract, and removes the claim and its workload when its conversation lease ends

#### Scenario: Template or pool mismatch
- **WHEN** the upstream template or pool does not match the configured image, runtime or deny-all network boundary
- **THEN** the broker refuses to start

### Requirement: Conversation-scoped execution
The system SHALL privately bind executions to user, team and conversation identity without adding identity to the model-visible tool schema. It SHALL serialize executions in the same conversation across broker replicas, retain the conversation's scratch files across active executions and supported suspension/resumption, and never share its workload or scratch with another conversation or user. The default final inactivity expiry SHALL be 20 minutes after the last execution.

#### Scenario: Reuse within a conversation
- **WHEN** the same authorized conversation executes code again before active-pod suspension
- **THEN** the broker executes in its private workload and can read scratch files written earlier

#### Scenario: Resume within the conversation deadline
- **WHEN** the same authorized conversation executes code after its pod was suspended but before final expiry
- **THEN** its private workload is resumed and can read its prior `/work` files

#### Scenario: Concurrent calls on different replicas
- **WHEN** the same conversation submits two code calls through separate brokers
- **THEN** those calls execute serially in one conversation workspace

#### Scenario: Isolation between conversations
- **WHEN** a different conversation or user executes code
- **THEN** it receives a different workload and cannot read the first conversation's scratch files

#### Scenario: Idle expiry
- **WHEN** no execution occurs in a conversation for the configured final idle period
- **THEN** its workload, persistent scratch and mounted source binding are removed, and the next execution starts a fresh workspace

## ADDED Requirements

### Requirement: Frugal idle suspension
On an approved persistent-workspace profile, the broker SHALL remove a conversation's running pod after a shorter operator-approved active-idle period while retaining only its private workspace and metadata until final expiry. It SHALL keep zero unassigned running workloads. A backend that cannot preserve the required workspace SHALL reject that profile rather than silently discard files.

#### Scenario: Active idle period elapses
- **WHEN** a conversation has no execution for the active-idle period but has not reached final expiry
- **THEN** its running pod stops consuming active sandbox capacity and `/work` remains private and recoverable

#### Scenario: Input and skill mounts after resume
- **WHEN** a suspended sandbox resumes
- **THEN** its `/inputs` and `/skills` are mounted read-only under the current authorization rules, and its `/work` is writable only for that conversation

#### Scenario: Unsupported persistence profile
- **WHEN** an operator enables idle suspension without an approved persistent workspace backend
- **THEN** deployment or broker startup fails before accepting executions

### Requirement: Broker restart and pressure control
The shared coordinator SHALL survive broker restarts without deleting another replica's active conversation. It SHALL reclaim abandoned reservations and expired workspaces, and SHALL bound simultaneous sandbox creations and Kubernetes control-plane requests. A restarted broker SHALL validate an existing workload before executing in it.

#### Scenario: Broker restart
- **WHEN** one broker replica restarts while another owns active conversations
- **THEN** the restart does not delete those workloads or admit above the shared cap

#### Scenario: Abandoned preparation
- **WHEN** a broker dies while provisioning a workload
- **THEN** a later reconciliation either safely adopts or removes the orphan before returning its capacity

#### Scenario: Burst of requests
- **WHEN** many first executions arrive together
- **THEN** only the bounded number of preparations run concurrently and excess requests wait or fail predictably without an unbounded Kubernetes API burst
