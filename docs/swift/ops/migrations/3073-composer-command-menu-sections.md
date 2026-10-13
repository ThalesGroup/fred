---
schema: 1
title: "Section the chat composer command menu by source and show invoked commands as containers"
impact: none
configuration: none
configuration_reason: "Frontend display of the slash command menu and of invoked commands only; no configuration key, chart value or permission changes."
no_action_reason: "The menu reads the same team, personal and skill catalogs as before; no API, stored data or runtime change."
---
## Applicability

All Fred deployments using managed chat.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

In a team conversation, type `/` in the empty composer: the menu lists the
team's commands under a heading carrying the team name, then the user's own
commands under "Personal space", then the platform skills, whatever the agent.
Pick a command and a skill: each shows as a small coloured container in the
field and, once sent, in the message.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Users now see their personal-space commands with every agent, not only some of
them; a command typed without picking a row still runs the team's one first.
