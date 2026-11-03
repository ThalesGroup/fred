## Why

A pod with one manually declared chat profile but no explicit `default_profile_by_capability.chat` currently has no chat default. This unnecessarily blocks ordinary chat and prompts administrators to choose the only available manual model.

## What Changes

- Infer the pod chat default from its sole manual chat profile when no chat default is declared.
- Keep an explicit YAML default authoritative. Do not infer a default from discovered profiles or when multiple manual chat profiles exist.
- Advertise the effective default in the pod model catalog so the control plane and admin warning match actual routing.
- Reuse the existing platform binding table and migration; no database schema change is needed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-routing`: Define the sole-manual-chat default and its advertised behavior.

## Impact

`libs/fred-runtime` catalog policy and pod catalog projection, focused tests, model routing documentation, and the existing draft PR for issue #3230.
