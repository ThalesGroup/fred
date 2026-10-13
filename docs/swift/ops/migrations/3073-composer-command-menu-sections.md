---
schema: 1
title: "Section the chat composer command menu by source and allow several prompt commands in one message"
impact: minor
configuration: none
configuration_reason: "Display of the slash command menu and one optional field on the turn's command descriptor; no configuration key, chart value or permission changes."
---
## Applicability

All Fred deployments using managed chat, including agent pods built outside
this repository on `fred-runtime`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. No data
migration: the new field is stored inside the existing
`session_history.metadata_json` column.

## Configuration

No configuration changes are required.

## Upgrade

Follow this order:

1. Upgrade the runtime pods first: `fred-agents` and every other agent pod
   built on `fred-runtime`. A pod built outside this repository has to be
   rebuilt on the `fred-sdk`, `fred-core` and `fred-runtime` of this release.
2. Then upgrade the frontend.

The other order is safe for the agents and for stored data. Its only effect is
described under Limitations, for the messages sent while a runtime pod is
still on the previous release.

## Validation

In a team conversation, type `/` in the empty composer: the menu lists the
team's commands under a heading carrying the team name, then the user's own
commands under "Personal space", then the platform skills, whatever the agent.
Pick a command with Enter: it is added to the field as a small coloured
container and nothing is sent; press Enter again to send. A skill behaves the
same way, and both keep their container in the sent message. Click the
command's container in the field: a side panel shows the prompt's text.

Then send a message holding two commands, for example `/summary then /tone`:
the message shows one container per command, and clicking one opens that
prompt's own text. Reload the page: both containers are still there. If only
the first one is, the pod that ran the turn is still on the previous release.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A message holding several commands and sent through a runtime pod that is not
upgraded yet is answered normally: the agent receives the text of every
prompt. After a page reload, such a message shows its first command as a
container and the following ones as the `/name` the user typed, and the side
panel shows the whole text that was sent. Messages stored that way keep that
display after the pod is upgraded.

A message holds at most 16 prompt commands.

Users now see their personal-space commands with every agent, not only some of
them; a command typed without picking a row still runs the team's one first.
Enter on a command in the menu no longer sends the message at once: it adds
the command, and a second Enter sends.
