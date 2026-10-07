---
schema: 1
title: "Retire the team-level Mon espace file area"
impact: major
configuration: none
configuration_reason: "No configuration key or default changes; the existing resource-spaces flag now controls only team-shared and agent tabs."
---

## Applicability

Deployments whose users or agent tools access `Mon espace` at
`/teams/{team_id}/users/{uid}` through Knowledge Flow `/fs`.

## Prerequisites

Export any personal-area files that must remain accessible. This change leaves
their bytes in object storage but removes product and API access to that path;
it does not migrate them to agent or team-shared files. Review authored tools
that call `ToolContext.read_user()` or implement `WorkspaceFsPort.read_user_bytes()`.

## Configuration

No configuration keys change. `enableAllResourceSpaces` continues to gate the
team-shared and agent tabs; its description changes to reflect those two tabs.

## Upgrade

Deploy the frontend, Knowledge Flow, SDK, and runtime updates together. The
Resources page now offers Corpus, team-shared files, and agent files. `/fs`
rejects the retired team-level personal path for listing, reading, mutation,
search, and copy operations. Per-agent `agents/{agent}/users/{uid}` paths and
team-shared paths remain supported. `resolve_template()` checks the agent's
own `templates/` directory before team-shared `templates/`.

## Validation

Confirm the Resources page has no Mon espace tab and `/fs` rejects the retired
path while agent-owned and shared files remain accessible.

## Rollback

Rolling back the code restores access to the retained personal-area objects.
No object-store migration or deletion is performed by this change.

## Limitations

This change does not decide when to export or delete retained personal-area
objects; that requires a separate storage-retention decision.
