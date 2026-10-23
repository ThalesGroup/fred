## Why

`default_profile_by_capability.chat` is a deployment default for one agent pod, while the existing admin model binding forces one model across all managed turns. Administrators need to change each pod's default without editing its YAML or replacing user and team choices.

## What Changes

- Add a platform-admin setting for the chat default of each configured agent pod, selected from that pod's advertised chat profiles.
- Apply a saved pod default only at the pod-default routing level; retain the YAML default when no override exists or a saved discovered profile is unavailable.
- Give each pod a manual-catalog fallback for a selected discovered profile that disappears; use the manual YAML default when no fallback override exists.
- Present a "Model defaults" panel with "Agent pods" and "Platform" tabs. The pod tab shows default and fallback selectors per detected pod. The platform tab preserves the existing manual provider/name/settings form for its global override.
- Keep static-only deployments and existing global bindings working as before.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-routing`: Admin-managed per-pod defaults and their routing precedence.

## Impact

Control-plane admin API and persistence, managed runtime binding, chat routing and composer projection, generated frontend client, Models admin UI, and the existing PR migration.
