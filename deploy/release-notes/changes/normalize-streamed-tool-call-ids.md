---
schema: 1
title: "Preserve tool-call IDs in Chat Completions streams"
impact: minor
configuration: production
configuration_reason: "The pod AI configuration and Helm charts expose an optional deployment switch for the shared Python transport correction, enabled by default."
---

## Applicability

Fred model profiles using OpenAI-compatible or Azure Chat Completions streaming.

## Prerequisites

Use the normal deployment procedure.

## Configuration

Normalization is enabled by default for successful Chat Completions SSE responses.
The correction removes the literal string `"null"` from continuation IDs only when
an earlier fragment identified the same call; it preserves its argument fragments.

Weaver exposes a deployment-only switch for all admitted models in one pod:

```yaml
ai:
  normalize_streamed_tool_call_ids: true
```

Set it to `false` to diagnose provider compatibility, then restart the affected
pod. With the Fred chart, use
`applications.fred-agents.configuration.ai.normalize_streamed_tool_call_ids`;
with the standalone agent-pod chart, use
`configuration.ai.normalize_streamed_tool_call_ids`. Both default to `true`.
There is no UI toggle, per-offer policy, permission change, or database field.

The shared Python factory retains Swift's per-model
`ModelConfiguration.settings.normalize_streamed_tool_call_ids` option. Weaver's
admitted calls receive the pod switch through their existing model factory;
operators do not configure a separate model catalogue in the pod.

## Upgrade

Deploy the updated Python workloads normally. The switch defaults to enabled
when omitted. Changing it requires restarting all replicas of the affected pod.
No database migration is introduced.

## Validation

Run a streaming turn that calls a tool. Check that the tool receives complete
arguments and that the model continues after its result.

## Rollback

Set the pod switch to `false` and restart the affected replicas if a regression
is confirmed. Restore `true` to re-enable the repair. For an image rollback,
remove the new configuration key before deploying an image whose schema does
not support it. There is no data migration.

## Limitations

The correction applies to incoming Chat Completions streams. Previously saved
conversation history is outside its scope. Responses API, non-streamed replies
and the Rust Ralph client are unaffected. The Grafana corrected-stream counter
counts transport corrections, not completed tool executions; its new panel keeps
Weaver namespace/pod filtering and a unique panel ID. Provider reception is still
required after deployment.
