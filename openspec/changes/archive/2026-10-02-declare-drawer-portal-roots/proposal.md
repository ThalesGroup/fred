## Why

PR #2890 exposes a drawer whose keyboard cycle cannot discover raw React portals before focus enters them. Explicit consumer-owned portal roots make their controls reachable without React internals or focusing unrelated page controls.

## What Changes

- Add optional `portalRoots` to InlineDrawer for dedicated raw-portal containers.
- Include connected, visible controls in those roots in both directions of the modal keyboard cycle; retain nested Dialog handling and opener restoration.
- Verify real keyboard traversal in the packed consumer and document the declaration requirement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: explicit drawer portal focus scope.

## Impact

InlineDrawer public props and focus traversal, neutral consumer fixture, browser smoke, existing package spec and migration note. No backend, evaluator-specific behavior, or new dependency. Developer approved the optional portalRoots approach in this task.
