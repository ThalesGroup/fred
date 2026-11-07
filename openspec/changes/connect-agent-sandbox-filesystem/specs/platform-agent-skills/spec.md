## MODIFIED Requirements

### Requirement: Skill file access stays within the declared skill

Web selections and ReAct loading SHALL resolve a catalog name on the server. ReAct reference reads SHALL resolve a relative file path within that skill's published directory, support bounded UTF-8 text and reject traversal, absolute host paths, escaping symlinks, unsupported content and writes. Deep native access SHALL follow the separate physical-filesystem requirement: current files remain confined to the configured root, without per-skill snapshot filtering. Skill file access SHALL NOT expose arbitrary host or conversation files, install tools or grant permissions. A frontmatter tool hint SHALL NOT be treated as a permission grant or an enforced restriction. A script bundled with an operator-published skill MAY be projected for execution only when the agent has the separate `code_sandbox` capability; reading or selecting a skill alone SHALL NOT execute its scripts.

#### Scenario: Read an associated template

- **WHEN** a ReAct agent reads `references/meeting-minutes-template.md` from the valid `meeting-minutes` skill
- **THEN** it receives that snapshot's reference text without needing general filesystem access

#### Scenario: Escape or write attempt

- **WHEN** a ReAct request attempts to read outside the selected skill or modify its files
- **THEN** the operation is refused without returning unrelated file contents

#### Scenario: Script requires sandbox capability

- **WHEN** a published skill includes a Python script and the agent lacks `code_sandbox`
- **THEN** skill discovery and instruction reads remain available but script execution is refused

## ADDED Requirements

### Requirement: Published skill scripts retain source boundaries
The platform SHALL publish supported script files from an approved skill package without following escaping links or accepting arbitrary model-supplied host paths. An enabled sandbox SHALL read those files through a read-only skill mount without pre-copying them into writable guest scratch. A future user skill source SHALL use the same mount contract only after its own publication and authorization checks exist.

#### Scenario: Published Python script
- **WHEN** an authorized agent runs a script from an approved platform skill
- **THEN** the script bytes come from that skill's published files through a read-only mount in its conversation sandbox

### Requirement: Skills declare sandbox dependency without changing ordinary skill access
A published skill MAY declare that its procedure requires `code_sandbox`. The catalog and agent guidance SHALL identify that dependency. If the capability is disabled or its approved mount is unavailable, the agent SHALL report that the dependent procedure cannot run, while existing skills and document tools continue to work as before.

#### Scenario: Ordinary skill without sandbox
- **WHEN** `code_sandbox` is disabled and an agent loads a skill that does not require it
- **THEN** catalog discovery, instruction and reference reads, selection and existing document tools retain their current behavior

#### Scenario: Sandbox-dependent skill without sandbox
- **WHEN** `code_sandbox` is disabled and an agent selects a skill that declares that dependency
- **THEN** it can read the skill's instructions but is told that execution is unavailable and does not claim to have completed the script-dependent procedure
