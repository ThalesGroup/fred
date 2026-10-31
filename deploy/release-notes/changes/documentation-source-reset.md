---
schema: 1
title: "Replace legacy documentation with the current architecture entry point"
impact: none
configuration: none
configuration_reason: "Documentation and release-note tooling paths change; application and chart configuration are unchanged."
no_action_reason: "The cleanup changes repository guidance and CI note locations, without changing deployed services or persisted data."
---

## Applicability

Contributors using this checkout and maintainers preparing future Fred releases.

## Prerequisites

Use the checkout's release-note tooling and policy together.

## Configuration

No application configuration changes. The release-note policy now uses
`deploy/release-notes/changes` and `deploy/release-notes/releases`.

## Upgrade

Deploy normally. For repository work, start with the architecture dossier and
component READMEs. Previous RFCs, Swift docs and OpenSpec content remain in Git
history. Add new operator notes to the fresh changes directory.

## Validation

Validate this note with `scripts/migration_guides.py check-pr --worktree` and
an explicit base ref. Confirm release workflows attach guides from the new path.

## Rollback

Revert the documentation and tooling-path change together if needed. There is no
database or deployed-service migration in this change.

## Limitations

Claude and Codex skills and agent instructions are updated separately. The first
release crossing the fresh history boundary requires a reviewed legacy-range
note; this cleanup does not claim that older deployments can upgrade safely.
