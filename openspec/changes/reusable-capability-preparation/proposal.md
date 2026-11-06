# Proposal

## Why

Swift's PPT Builder currently makes a capability and its agent pod own template storage, background execution and readiness, including a process-local model handle. This ties long-running preparation to a particular replica and makes the same lifecycle difficult to reuse for another capability. Weaver provides a useful worker and control-plane split, but its PPT-specific admission and single preparation slot should not be copied unchanged.

## What Changes

- Introduce a reusable capability-preparation contract: the control plane owns durable asset references, admission, job state and aggregate agent readiness; a dedicated worker dispatches installed capabilities and owns no PPT-specific branch.
- Move PPT template preparation to that contract. The PPT capability retains template analysis, vision labelling rules, derived artifacts and deck rendering. Preserve Swift's platform-wide default template and author review behavior.
- Use Knowledge Flow's configured `vision_model` for PPT slide labelling through an authenticated internal API. Keep the PPT-specific prompt, response parsing and validation in the capability. Keep the "Use a vision model" toggle, but remove every model selector.
- **BREAKING**: Remove the global `supports_vision` model-catalog property and its SDK, runtime, control-plane and frontend projections. Existing saved PPT model selections are ignored and removed during migration; `use_vision` remains.
- Migrate existing Swift PPT templates, successful inventories, overrides and platform default without requiring users to upload again; make cutover safe across replicas and retries.

## Capabilities

### New Capabilities

- `capability-preparation`: Durable, capability-neutral preparation admission, execution, status, asset lifecycle and agent readiness.

### Modified Capabilities

- `ppt-builder`: Template preparation, vision source, settings, failure handling and platform default behavior.
- `model-routing`: Public model catalog and routing projections no longer advertise `supports_vision`.

## Impact

- Control plane agent/capability APIs, persistence, object storage and Temporal orchestration; fred-sdk capability contract; fred-runtime and the `fred-agents` worker deployment.
- PPT Builder capability, legacy analysis data migration, agent form and Admin > Features settings UI.
- Knowledge Flow internal vision endpoint, service authentication, timeouts and deployment configuration.
- Model catalog YAML/schema/API and generated frontend types; existing clients reading `supports_vision` must tolerate its removal.
