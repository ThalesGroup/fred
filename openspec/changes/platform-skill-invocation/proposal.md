## Why

Packaged procedures are inconsistently enabled and explicit Deep selections rely on model-chosen reads. Invocation controls must distinguish user requests from autonomous use.

Tracking: #3299, #3300, #3302. Scope and acceptance approved in the conversation on 2026-10-27; developer explicitly requested the complete local implementation.

## What Changes

- Enable packaged skills when configuration is omitted, retain explicit null opt-out and custom directories.
- Enforce user-invocable and disable-model-invocation throughout discovery and reads.
- Use native pinned_skills for explicit Deep requests with truthful attribution.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: Packaged procedures are inconsistently enabled and explicit Deep selections rely on model-chosen reads. Invocation controls must distinguish user requests from autonomous use.

## Impact

SDK skill metadata, runtime configuration/loaders/execution, Helm and generated schemas, existing skill tests.

## Non-goals

No push/PR, skill editing UI, per-team/agent enablement, new tools or execution permissions.

