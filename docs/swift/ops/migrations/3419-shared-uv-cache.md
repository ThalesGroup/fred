---
schema: 1
title: "Reuse uv's default package cache across worktrees"
impact: none
configuration: local
configuration_reason: "Only the Makefile's build-time uv cache default changes; deployed application configuration and chart values are unaffected. Explicit UV_CACHE_DIR settings remain supported."
no_action_reason: "No runtime behavior, stored data or deployment steps change; uv selects its normal cache automatically during builds."
---

## Applicability

Developers and build jobs using the shared Python Makefile variables.

## Prerequisites

The selected uv cache directory must be writable by the build user.

## Configuration

Make no longer defaults UV_CACHE_DIR to each project's target/.uv-cache.
uv uses its normal cache selection, allowing reuse across worktrees.
Restricted build environments can set UV_CACHE_DIR to a writable directory.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

Check that uv cache dir reports the same cache from different worktrees
when no explicit cache override is set. Each project retains its own .venv.

## Rollback

Revert the Makefile change or explicitly set UV_CACHE_DIR to the desired path.
No data migration is involved.

## Limitations

The shared cache warms on first use; existing project-local caches are not moved.
Explicit cache overrides still take precedence over uv's normal default.
