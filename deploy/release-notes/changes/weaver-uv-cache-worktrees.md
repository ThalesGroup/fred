---
schema: 1
title: "Reuse the uv cache across worktrees"
impact: none
configuration: none
configuration_reason: "The makefile no longer overrides uv's cache location; runtime configuration is unchanged."
no_action_reason: "uv selects its normal shared cache automatically and no deployment setting or data changes."
---
## Applicability

Contributors using uv from multiple Fred worktrees.

## Prerequisites

No additional prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Use the usual development commands. uv will reuse its normal cache location.

## Validation

Run uv in two worktrees and confirm that downloads are reused.

## Rollback

Restore the previous makefile if worktree-local caches are required.

## Limitations

Existing worktree-local caches are not migrated or removed automatically.
