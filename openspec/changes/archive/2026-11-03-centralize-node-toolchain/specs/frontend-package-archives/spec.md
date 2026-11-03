## MODIFIED Requirements

### Requirement: Release validation uses an exact producer toolchain

Candidate generation and release-evidence production SHALL require exact, non-floating Node and npm versions recorded in the release contract. The root .nvmrc SHALL define the exact current repository Node baseline. The selected baseline SHALL use the Node version from .nvmrc with npm 11.19.0 for both producer and application validation. Current release contracts and active development, CI and build-image entry points MUST agree with that Node baseline. Changing either pin MUST be a reviewed contract change with renewed validation. Historical release records MUST retain the exact versions that produced their evidence.

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

#### Scenario: Repository baseline changes

- **WHEN** a maintainer updates the root .nvmrc
- **THEN** developer startup, CI and active build images use the new exact version and affected validation is selected
- **AND** a mismatching current release contract fails before new evidence is produced
