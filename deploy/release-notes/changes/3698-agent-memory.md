---
schema: 1
title: "Agent memory capability"
impact: minor
configuration: none
configuration_reason: "The memory capability ships in the fred-agents image and is offered through the existing capability catalogue; no environment variable, secret or chart value is added or changed."
---
## Applicability

Weaver deployments upgrading Control Plane, fred-agents and frontend.

## Prerequisites

Use the normal backup and schema-owner procedure.

## Configuration

No configuration changes are required.

## Upgrade

Run `control-plane init-schema` with the normal schema-owner identity to apply
SQLx migrations `0061_agent_memory.sql` and
`0062_agent_memory_note_revisions.sql`, then deploy matching Control Plane,
fred-agents and frontend versions.

The new `memory` capability (UI name "Memory") is opt-in: an organization
administrator offers it like any other capability, then an agent editor turns
it on for a ReAct agent. Each agent instance then keeps up to 50 short notes
(500 characters each), shared by every member of its space. The agent writes
notes itself and the chat shows each one with an Undo action; a note written
right after the agent read external content asks the person for approval first,
unless the agent editor turned that confirmation off. Agent editors list, add
edit and remove notes, and see removed notes, in the agent form's Memory tab.
An edited note keeps its place in the list and its previous version moves to
the history.

## Validation

Offer the memory capability and enable it on an agent. In a chat, ask the agent
to remember a preference: a "Remembered" card appears; click Undo and verify it
reads "Removed from memory". Open the agent's settings: the Memory tab lists the
active notes and the removed one under History.

## Rollback

Roll back Control Plane, fred-agents and frontend together. An older Control
Plane binary rejects the newer SQLx migration history; restore a matching
pre-upgrade database backup with the prior binaries. Do not remove migration
receipts manually.

## Limitations

Memory is available to ReAct agents only.
