# Proposal

## Why

Some Mistral Chat Completions streams send the string `"null"` as the ID of argument continuations. LangChain can split one call into two, causing a nameless tool call or an invalid history rejected by the gateway.

## What Changes

- Normalize the quoted sentinel only after a real ID was established for the same choice and tool index. Enable this across Chat Completions routes by default with a per-model YAML opt-out.
- Preserve the original tool-call ID, per-index arguments, incremental delivery, and shared HTTP client behavior in sync and async calls.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-tool-call-recovery` adds normalization for native streamed tool-call continuations.

## Impact

Fred core model factory, shared HTTPX transports, and offline model regression tests. Existing saved conversations are outside the scope.
