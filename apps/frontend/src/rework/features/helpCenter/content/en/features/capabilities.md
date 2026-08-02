---
title: Agent capabilities
order: 50
description: The extra functions an agent can call on, enabled per team.
icon: extension
---

# Agent capabilities

A **capability** extends what an agent can do beyond conversation: draft a
document, fill a template, query data… Capabilities come from the platform's
**feature catalog**: an administrator enables a feature for your team (see
[Admin console](/help/en/features/admin)), then your team's editors can turn
it on for the agents that need it, as one of that agent's capabilities.

## Enabling a capability

Enabling a feature for your team is an administrator's job. A feature not
enabled for the team isn't available to its agents as a capability; if an
enabled feature is later disabled, the agents that depend on it are
**suspended** until it's restored (see [Agents](/help/en/features/agents)).

## A few built-in capabilities

- **Writable document**: the agent drafts and evolves a document over the
  conversation. See the guide
  [Producing documents](/help/en/guides/generate-documents).
- **PowerPoint template filling**: from a `.pptx` template, the agent extracts
  the values and produces a finished presentation.
- **Tabular data**: load a tabular file and query it in natural language. See
  the guide [Querying tabular data](/help/en/guides/analyze-tabular-data).

The exact catalog depends on your platform's configuration.
