## Purpose

Allow developers to operate a dedicated local Fred installation through the factory while keeping product-specific lifecycle behavior in the product checkout.

## ADDED Requirements

### Requirement: Dedicated local Fred data can be reset without rebuilding infrastructure
The factory SHALL expose an explicit application reset command delegated to the selected product. Fred SHALL preview its reset without mutation by default and require explicit confirmation for deletion. It SHALL retain the cluster, PVCs, installed images, foundation secrets and Keycloak accounts/clients. Reset SHALL clear Fred SQL business data, consent, bootstrap state, authorization, search indexes, stored content and Temporal work coherently, including manager when installed. It MUST refuse shared or unsupported storage installations before mutation and MUST NOT build images or reinstall infrastructure.

#### Scenario: Developer previews reset
- **WHEN** the reset command is called without confirmation
- **THEN** it lists the targeted services and data and the preserved identities
- **AND** it does not change deployments or data

#### Scenario: First-user journey is repeated
- **WHEN** a confirmed reset succeeds on the supported dedicated installation
- **THEN** the same Keycloak account can log in and must accept the active terms and bootstrap the first administrator again
- **AND** imported organizations, teams, projects, memberships and content are absent
- **AND** installed application images are reused

#### Scenario: Shared installation is refused
- **WHEN** another application, unsupported storage configuration or active producer outside the supported deployment set is detected
- **THEN** reset fails before deleting data or stopping any service

### Requirement: Reset failures do not restart applications over partially cleared data
Reset SHALL stop application producers and wait for them to exit before deleting data. It SHALL initialize database schemas using the installed migration definitions before restoring the original replica counts. A failure SHALL leave applications stopped and report a retry procedure; a retry MUST NOT forget the original replica counts. Success SHALL require restored deployment readiness. Concurrent reset invocations through the same factory checkout MUST NOT interleave for a target, including invocations selecting different product checkouts.

#### Scenario: Cleanup fails after stopping applications
- **WHEN** any storage cleanup or schema initialization fails
- **THEN** reset reports failure and leaves application services stopped
- **AND** a retry for the same deployments can repeat cleanup and restore the saved replica counts

#### Scenario: Deployed application changes during a failed reset
- **WHEN** a retry finds a different deployment identity or image configuration
- **THEN** it refuses to apply the stale restoration state

#### Scenario: Migration fails
- **WHEN** an installed SQL migration Job fails during reset
- **THEN** application deployments are not restarted and reset does not report success
