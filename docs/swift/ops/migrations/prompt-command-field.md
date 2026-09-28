---
schema: 1
title: "Add an optional command to team prompts"
impact: minor
configuration: none
configuration_reason: "The feature is carried entirely by a schema change and application code; no configuration key, default, or chart value changes."
---
## Applicability

Existing Fred deployments upgrading to this release. Every deployment runs the
schema change; no team is affected until someone authors a command.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Run the control-plane Alembic migration as part of the normal deployment. It
adds a nullable `command` column to the `prompt` table and a partial unique
index on `(team_id, command)` restricted to rows where the command is present.

No data migration: every existing prompt keeps a null command and behaves
exactly as before. The index is partial, so any number of prompts may carry no
command while a present one stays unique within its team.

A prompt may now carry an optional command — a lowercase unaccented slug of at
most 64 characters — which a later release will use to run the prompt from the
chat composer. Nothing invokes it yet; this release only lets teams author it.
Importing a published prompt copies its command and, where the destination
team already holds it, appends the first free `-N` suffix from `-2`, the same
treatment the prompt's name already receives.

## Validation

Open a team's prompt library, edit a prompt and set a command such as
`summary`; save and reopen it to confirm the value persists. Setting the same
command on a second prompt of that team must be refused with the conflict
shown on the command field. Importing the same published prompt twice into one
team must succeed both times, the second copy holding the `-2` variant.

## Rollback

The downgrade drops the index then the column. Any command authored since the
upgrade is lost — the expected cost of reverting the feature. Nothing else
about a prompt is affected.

## Limitations

The command is not yet usable from the chat composer; the trigger and its menu
ship in a later change.
