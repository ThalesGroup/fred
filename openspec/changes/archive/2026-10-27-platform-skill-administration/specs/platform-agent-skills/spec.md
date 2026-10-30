## ADDED Requirements

### Requirement: Feature managers administer packaged skills globally

Administration SHALL provide a global Skills tab under Features with packaged inventory, invocation modes, source availability and one enabled control per skill. Only feature-management permission SHALL allow administration. No exception SHALL mean enabled, including newly shipped skills. Shared persistent overrides SHALL have audit identity/time and atomic idempotent updates. Custom directories SHALL retain their existing behavior.

#### Scenario: Global opt-out across replicas
- **WHEN** an authorized manager disables a packaged skill
- **THEN** new loads from the next turn, including existing conversations and resumes on another replica, are denied in discovery, selections, pins, native reads/searches, loaders, children and capability access
- **AND** in-flight work and already-read history are preserved

#### Scenario: Concurrent independent updates
- **WHEN** two managers change different skills through separate instances
- **THEN** both changes remain persisted and affect the next server-resolved execution policy

#### Scenario: Mixed or unavailable runtime sources
- **WHEN** a source is unreachable or cannot enforce enablement
- **THEN** administration reports its status and does not claim effective global disablement
- **AND** legacy runtimes cannot resolve managed execution while active restrictions require unsupported enforcement
