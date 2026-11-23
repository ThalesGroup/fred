---
schema: 1
title: "Preserve tool-call IDs in Chat Completions streams"
impact: minor
configuration: none
configuration_reason: "Existing model configuration works as-is. Operators can optionally opt out through the existing model settings map."
---

## Applicability

Fred model profiles using OpenAI-compatible or Azure Chat Completions streaming.

## Prerequisites

Use the normal deployment procedure.

## Configuration

Normalization is enabled by default. For an individual model profile, set
`normalize_streamed_tool_call_ids: false` under its model `settings` to opt out.

```yaml
model:
  provider: openai
  name: mistral-medium-latest
  settings:
    normalize_streamed_tool_call_ids: false
```

## Upgrade

Deploy Fred normally. Apply the optional model setting only if the profile
should receive the original streaming deltas.

## Validation

Run a streaming turn that calls a tool. Check that the tool receives complete
arguments and that the model continues after its result.

## Rollback

Disable the normalization on the affected model profile or use the normal
deployment rollback. There is no data migration.

## Limitations

The correction applies to incoming Chat Completions streams. Previously saved
conversation history is outside its scope.
