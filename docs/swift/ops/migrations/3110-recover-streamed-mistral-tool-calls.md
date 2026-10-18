---
schema: 1
title: "Recover Mistral tool calls written as text in long reasoning turns"
impact: none
configuration: none
configuration_reason: "Only fred-runtime's tool-call recovery, content-block rendering and Mistral reasoning replay, and fred-core's log-scope string bound, change; no configuration key, default or chart value is involved."
no_action_reason: "No API, event, data or configuration change: a Mistral tool call written as text now runs as a tool call, empty provider blocks no longer appear as text, and Mistral gets its own reasoning back in the history, once the new runtime is deployed."
---
## Applicability

Existing Fred deployments upgrading to this release, including agent pods built on fred-runtime. The recovery only applies to Mistral models.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With a Mistral model and reasoning enabled, run a long agent turn that ends in a tool call. The tool runs instead of its JSON being printed as the answer, and no `{'type': 'reference', ...}` text or runaway text after the call appears in the chat. When recovery happens, the `agent.tool_call_text_recovered_total` counter increases.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

With a Mistral model and reasoning enabled, requests are larger because earlier reasoning is replayed: in the leak study the median model call took about 6 s longer (17.8 s to 23.8 s), while runs were as fast or faster because tool calls stopped being written as text (26/146 calls to 0/188) and runaway responses stopped (3 hangs to 0). Long conversations reach the history size budget sooner, so older messages are trimmed earlier.

Conversations already stored with the printed tool call keep that text; only new turns are affected.
