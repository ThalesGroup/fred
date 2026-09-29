---
schema: 1
title: "Run a team prompt from the chat by typing a command"
impact: none
no_action_reason: "The additive schema migration runs as part of normal deployment; existing prompts and conversations remain compatible, with no configuration, re-ingestion, or additional operator action required."
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
command while a present one stays unique within its team. Conversation history
needs no change either — it stores message metadata as a JSON document, which
already accepts the new key.

What the release gives users:

- A prompt may carry an optional **command** — a lowercase unaccented slug of
  at most 64 characters — authored on the team's prompt library by an editor.
- Typing `/` at the start of an empty chat composer opens the team's commands;
  arrows walk them, `Tab` completes, `Enter` runs, `Esc` closes. Sending a
  command sends the **prompt's text**, with any text typed after the command
  appended to it.
- The turn is recorded with the command it was launched from (`RuntimeContext`
  and the stored turn's metadata each gain an optional `command`) and the
  transcript renders it as that command, with the text actually sent one click
  away in a side panel.
- One new read endpoint,
  `GET /control-plane/v1/teams/{team_id}/prompt-commands`, which the composer
  resolves a typed command against. Additive; no existing endpoint changes
  shape.
- Importing a published prompt copies its command and, where the destination
  team already holds it, appends the first free `-N` suffix from `-2` — the
  same treatment the prompt's name already receives.

## Validation

Open a team's prompt library, edit a prompt and set a command such as
`summary`; save and reopen it to confirm the value persists. Setting the same
command on a second prompt of that team must be refused, with the conflict
shown on the command field. Importing the same published prompt twice into one
team must succeed both times, the second copy holding the `-2` variant.

In a conversation with that team, type `/` in the empty composer: the command
must be offered. Run it and confirm the turn shows `/summary` rather than the
prompt's text, and that the panel behind it holds the text that was sent.
Confirm every turn recorded before this release still renders as plain text.

## Rollback

The downgrade drops the index then the column. Any command authored since the
upgrade is lost — the expected cost of reverting the feature. A turn that
recorded a command before the rollback renders as its plain text afterwards:
degraded, not broken. Nothing else about a prompt or a conversation is
affected.

## Limitations

A command reaches only the prompts of the team the conversation belongs to, and
only prompts — platform skills stay model-facing. Text typed after a command is
plain continuation: named or structured parameters are a separate design.
