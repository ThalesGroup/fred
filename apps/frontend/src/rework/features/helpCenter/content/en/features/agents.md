---
title: Agents
order: 20
description: Create an agent from a template, configure it, manage its lifecycle.
icon: smart_toy
---

# Agents

An **agent** is an AI assistant configured for a specific purpose. Your team's
**Agents** page lists the available agents; it's also where you create new ones.

## Template and instance

Creation starts from a **template** — an agent blueprint provided by the
platform. You get an **instance**: your concrete agent, which you configure
freely and which belongs to your team. In chat, you always talk to an instance.

## Configuring an agent

At creation and at any time, an agent is tuned on several points:

- **The engagement prompt**: the permanent instructions that define its role,
  tone, and limits.
- **Attached prompts**: prompts from your library that complete its framing.
- **Resources**: the documents or libraries the agent can draw on to answer.
- **Capabilities**: the extra functions it can call on (see
  [Capabilities](/help/en/features/capabilities)).

![TODO: screenshot — agent configuration form](assets/agents-form.png)

## Lifecycle

- **Duplicate**: start from an existing agent to create a variant without
  reconfiguring everything.
- **Suspend**: an agent can be suspended — notably when a capability it depends
  on is disabled for the team. A suspended agent stays visible but is no longer
  usable until its dependency is restored.
- **Delete**: permanently remove an agent you no longer need.

> Creating and editing agents requires the **Editor** or **Administrator** role
> (see [roles](/help/en/getting-started/join-create-team)).
