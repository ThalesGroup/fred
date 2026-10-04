## Purpose

Defines the supported deployment-wide frontend feature flags and their fail-closed path from configuration to the authenticated browser experience.

## ADDED Requirements

### Requirement: Supported frontend flags remain typed and configurable

The platform SHALL expose a typed `feature_flags` object containing `enableApplications`, `enableAllResourceSpaces`, and `enableInformationSystems` in the authenticated frontend bootstrap. Each flag SHALL be independently configurable and default to `false` when omitted. The frontend SHALL resolve absent values as disabled through the shared flag hook.

#### Scenario: Configured supported flag

- **WHEN** an operator enables one supported flag in control-plane configuration
- **THEN** the authenticated bootstrap publishes it as enabled and the shared frontend flag hook resolves it as enabled

#### Scenario: Missing supported flag

- **WHEN** a supported flag is omitted from configuration or the bootstrap is not loaded
- **THEN** the feature resolves as disabled without enabling another flag

### Requirement: Deployment schemas reflect the supported flag surface

The control-plane configuration and Helm values schemas SHALL permit the supported frontend flags and SHALL reject unrecognized flag keys. The bundled Helm values SHALL retain the `enableApplications` configuration path.

#### Scenario: Supported Helm setting

- **WHEN** an operator validates a values overlay that sets a supported frontend flag
- **THEN** the chart schema accepts the flag and preserves its configured boolean value

#### Scenario: Retired Helm setting

- **WHEN** an operator validates a values overlay that sets an unrecognized frontend flag
- **THEN** the chart schema rejects the overlay before deployment
