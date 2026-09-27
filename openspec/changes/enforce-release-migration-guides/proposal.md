## Why

Fred's UI release notes do not provide a reliable operator migration procedure, and the release skill still defaults to patch increments irrespective of deployment work. With PR #2808 merged, migration information must become a required PR deliverable and a versioned release artifact before subsequent releases lose that knowledge.

Tracking: https://github.com/ThalesGroup/fred/issues/2809

## What Changes

- Require an English Markdown migration note on every PR, including an explicit no-operation declaration for documentation/internal changes.
- Validate metadata, operational sections and obvious migration/configuration risk in CI. Keep human review responsible for completeness and correctness.
- Generate a deterministic, versioned guide outside the frontend from the notes in the actual release range; preserve the note already supplied by PR #2808.
- Enforce a minimum paired code/chart version increment: patch for no additional operations, minor for operations including conditional activation, major for substantial incompatible change.
- Block tagged artifact publication if the guide or version check fails; attach the guide to the release.
- Update the shared release skill, PR template and development guidance to distinguish local configuration_prod.yaml from production chart values and private customer overlays.
- After the workflow lands and passes, make its PR status mandatory through GitHub protections. Do not alter existing unrelated checks or bypass policy.

## Capabilities

### New Capabilities

- `release-migration-guides`: Per-PR operational declarations, release aggregation, minimum version policy and publication validation.

### Modified Capabilities

None. Frontend package versioning and existing application/runtime contracts remain separate.

## Impact

Targets: `docs/swift/ops/migrations/`, `docs/swift/RELEASE-STRATEGY.md`, the configuration conventions, release helper/tests under `scripts/`, PR and publication workflows, PR template, `CLAUDE.md` and `.claude/skills/push-release/SKILL.md` (also discoverable through `.agents/skills`). No application runtime or database change, no private customer data required, no release tags or production rollout in this change.
