## ADDED Requirements

### Requirement: Fred deploys manager as part of its application composition
The reconstruction deployment SHALL build and deploy manager, knowledge-flow and frontend through the ordinary Fred command. It SHALL run exactly manager API/worker, knowledge-flow API/worker and frontend as application workloads, using one identical image reference per API/worker pair. It MUST NOT start control-plane, fred-agents or their migration workloads. Infrastructure services remain separate. Failed preparation SHALL stop deployment before removing an existing manager.

#### Scenario: The developer rebuilds Fred
- **WHEN** the developer runs `make k3d-app APP=fred DIR=../fred` with the reconstruction checkout
- **THEN** its manager, knowledge-flow and frontend images are built and selected together
- **AND** the five application workloads are managed by the Fred release without a separate manager command

#### Scenario: New installation has no legacy backends
- **WHEN** Fred is installed without control-plane or fred-agents services
- **THEN** the frontend, manager and knowledge-flow start successfully
- **AND** the existing UI remains available while calls to absent services fail explicitly

### Requirement: Integrating an existing manager preserves installation state
The deployment SHALL retire the known standalone manager release without changing its canonical data, authorization, user identities, consent, bootstrap state or foundation/model credentials. It MUST preflight ownership and refuse unexpected persistent resources before removal. Reruns SHALL converge without duplicate manager producers. Failures MUST retain data and identify a recovery path; completion requires ready application workloads.

#### Scenario: A provisioned installation is upgraded
- **WHEN** the existing standalone manager and Fred releases are migrated
- **THEN** existing organizations, memberships and folders remain accessible with the same IDs and grants
- **AND** only the Fred release manages the manager API and worker

#### Scenario: The old release owns persistent resources
- **WHEN** preflight finds a persistent volume claim or unexpected resource in the standalone release
- **THEN** migration fails before removing that release or its resources

#### Scenario: The deployment is repeated after migration
- **WHEN** the same command is run after successful integration
- **THEN** it upgrades the same five application workloads and does not recreate a standalone manager release
