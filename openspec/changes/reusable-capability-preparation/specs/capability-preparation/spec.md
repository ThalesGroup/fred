# Spec Delta

## Purpose

Defines how capabilities prepare durable resources before an agent can use them, with one shared lifecycle that remains correct across replicas and can serve more than one capability on an agent.

## ADDED Requirements

### Requirement: Capabilities declare preparation without a capability-specific control-plane path

The system SHALL accept preparation requests for any installed capability that declares a preparation contract. The control plane SHALL manage admission, durable input references and status without interpreting that capability's resource format or running its analysis.

#### Scenario: Another capability opts in

- **GIVEN** an installed capability other than PPT Builder declares preparation and receives a valid resource
- **WHEN** an authorized editor saves the agent
- **THEN** the same admission, status and worker dispatch path prepares that capability without a new capability-specific control-plane branch

#### Scenario: Capability unavailable on the target pod

- **WHEN** a save requests preparation for a capability not installed on the target pod
- **THEN** admission fails clearly and no job is accepted

### Requirement: Preparation input and results survive replica changes

The system SHALL store immutable input references and committed results in shared durable storage. A job SHALL be identified by its owner (agent or platform), capability, input revision and preparation rules version. Repeated saves of an already successful revision SHALL reuse its result.

#### Scenario: Save and worker land on different replicas

- **WHEN** one replica accepts a resource and another worker replica performs preparation
- **THEN** the worker reads the same input and all serving replicas can read the committed result

#### Scenario: Identical save

- **WHEN** an editor saves an unchanged resource and preparation settings after a successful preparation
- **THEN** no duplicate job is scheduled and the existing result remains in use

#### Scenario: Aggregate upload limit

- **WHEN** a multipart save contains several individually valid files whose combined bytes exceed 64 MiB
- **THEN** admission rejects the request before retaining all payloads or scheduling preparation

### Requirement: Preparation is recoverable and stale results are fenced

The system SHALL durably track pending, running, succeeded and failed preparations. Interrupted work SHALL be retried with bounded attempts, and only the current input revision SHALL be allowed to publish a result. Superseded or deleted resources SHALL be reclaimed after their readers and in-flight attempts release them.

#### Scenario: Worker stops mid-job

- **WHEN** a worker stops while preparing an input
- **THEN** another worker can resume or retry the job without a new user save

#### Scenario: Worker loses its activity lease

- **WHEN** an active worker stops sending heartbeats before the job deadline
- **THEN** Temporal retries the activity on a live worker before its two-hour start-to-close limit

#### Scenario: Replacement overtakes an old result

- **WHEN** resource B replaces A while A is running and A completes afterward
- **THEN** A cannot overwrite B's status or result, and B remains the revision used by the agent

#### Scenario: Delete during preparation

- **WHEN** an agent or capability resource is deleted during preparation
- **THEN** a later job completion cannot restore it or make the agent available

### Requirement: Agent readiness aggregates all required preparations

The system SHALL evaluate every selected capability's current preparation independently. An agent SHALL be usable only when every required preparation succeeded for its current revision and its other availability rules permit use. A preparation failure SHALL name the affected capability and remain visible to authorized editors.

#### Scenario: Two capabilities prepare concurrently

- **GIVEN** an agent has two preparing capabilities
- **WHEN** one succeeds and the other remains pending or fails
- **THEN** the agent stays unavailable and its status identifies the pending or failed capability

#### Scenario: Both preparations succeed

- **WHEN** all current preparations succeed
- **THEN** the agent becomes available without another save if no other rule suspends it

#### Scenario: Worker publishes while the binding is read

- **WHEN** a worker publishes a result while a serving pod resolves an agent binding
- **THEN** the binding has either a blocked verdict or the matching result reference, never a ready verdict without that reference

#### Scenario: Existing suspension persists

- **WHEN** preparation succeeds while the agent is separately suspended
- **THEN** preparation does not clear that suspension

### Requirement: Preparation operations enforce caller and service authorization

The system SHALL authorize resource writes, status reads and result reads against the agent and team. Worker access SHALL use a service identity scoped to the job, and capability data SHALL not be exposed through a public preparation endpoint.

#### Scenario: Unauthorized status request

- **WHEN** a caller without edit permission requests an agent's preparation details or output
- **THEN** the request is denied without exposing the resource or result

#### Scenario: Worker accesses another job

- **WHEN** a worker identity requests an input outside its authorized job scope
- **THEN** the request is denied
