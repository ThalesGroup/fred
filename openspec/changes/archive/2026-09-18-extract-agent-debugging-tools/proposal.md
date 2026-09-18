# Proposal

## Why

Managed-instance debugging currently requires ad hoc execution scripts and trace queries.
Extract the approved reusable workflows from the POC for [issue #2737](https://github.com/ThalesGroup/fred/issues/2737).

## What Changes

- Add shared conversation inspection and managed-instance test skills.
- Reuse CLI authentication and streaming client, preserve final events and explicit failure evidence.
- Replace custom delegation assumptions with native `task` and identifier-based attribution.

## Capabilities

No product capability changes: developer tooling and documentation only (`skip_specs: true`).

## Impact

Only `.claude/skills/` (also discovered through the existing `.agents/skills` symlink).
No runtime, authorization, API or storage contract changes.
