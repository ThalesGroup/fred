## ADDED Requirements

### Requirement: Frontend tooling supports only Node 24

The frontend application, shared package producer and distributed frontend package manifests SHALL declare Node >=24.21.0 <25 as their supported engine range. Repository installation and build entry points SHALL reject Node versions outside that range with actionable upgrade guidance before installing dependencies or building. Active setup instructions, CI jobs and development/build images SHALL agree with this support policy.

#### Scenario: Supported Node version

- **WHEN** a developer uses Node 24.21.0 or a later Node 24 patch with the supported npm tooling
- **THEN** ordinary installation, build and test entry points accept the Node version

#### Scenario: Unsupported Node version

- **WHEN** a developer invokes repository installation or build entry points under Node 22, a Node 24 version below 24.21.0, or Node 25 or newer
- **THEN** the command fails before dependency installation or build and identifies the required Node range

#### Scenario: Packed package advertises its supported engine

- **WHEN** an isolated consumer inspects any of the three packed frontend packages
- **THEN** its manifest declares Node >=24.21.0 <25 and no Node 22 support

## MODIFIED Requirements

### Requirement: Release validation uses an exact producer toolchain

Candidate generation and release-evidence production SHALL require exact, non-floating Node and npm versions recorded in the release contract. The selected baseline SHALL be Node 24.21.0 with npm 11.19.0 for both producer and application validation. Changing either pin MUST be a reviewed contract change with renewed validation.

FRED application tests that participate in compatibility validation MUST remain under their separately controlled application toolchain. Release evidence MUST record exact Node and npm versions for that application-test environment. Release orchestration MUST identify which toolchain produced each item of evidence and MUST pass immutable candidate archives between producer and application-test environments rather than resolving the producer's installed dependencies from the application environment. Matching toolchain pins MUST NOT remove that separation.

#### Scenario: Candidate production uses the pinned versions

- **WHEN** a release-candidate command starts with Node or npm different from the exact selected versions
- **THEN** it fails actionably before packing or recording candidate evidence

#### Scenario: Application compatibility runs on its own tooling

- **WHEN** CI executes FRED application regression or production-host compatibility checks against candidate archives
- **THEN** the application uses the selected application tooling and receives the exact candidate bytes without using the producer dependency tree

#### Scenario: The toolchain pin changes

- **WHEN** maintainers select a different exact Node or npm version
- **THEN** all three archives and their release evidence are regenerated and revalidated
