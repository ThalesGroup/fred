# Design

## Context

See `proposal.md` for the incident. ReAct currently sanitizes checkpoint messages, applies a message-count tail trim, handles reasoning replay, then applies a character-count tail trim to the model request. The trims can remove an entire completed turn. Neither changes the checkpoint. The current limits are 500 messages and 200,000 characters.

## Goals / Non-Goals

**Goals:** Select a bounded, valid model-input history that retains the latest completed user request and assistant answer alongside the active turn. Keep the selection policy independent of the budget unit.

**Non-Goals:** Summarize tool output with another model, change durable checkpoints, infer the provider's exact token count, or alter Deep and Graph history handling.

## Decisions

### Pure compaction with caller-supplied measurement

Add a helper below `react/` that receives messages, a budget, and a function measuring a candidate message sequence. The helper returns a new model-input list and never edits the input messages. ReAct invokes the same helper for message count and character count. A later token-aware caller can supply its own measurement and available input-token budget without changing the selection policy. A fixed character calculation inside the helper would duplicate that policy when token accounting becomes available.

### Preserve turn boundaries and an anchor

When input exceeds a budget, preserve leading system messages, including the team leader context injected into child ReAct calls. Split later messages at user-message boundaries. For each completed prior turn, retain its user message and final assistant answer and omit intermediate tool rounds. Preserve the active user message. If its complete tool rounds still exceed the budget, remove the oldest rounds as whole call/result groups while retaining the latest group. Project completed turns from newest to oldest, with a caller-supplied bound when available, then find the longest recent suffix that fits by monotonic binary search. Retain the latest completed turn as an anchor. An incomplete prior turn has no final answer and is omitted during compaction. The helper returns an over-budget candidate if the protected context cannot fit; the caller rejects it explicitly.

### Apply both limits to the actual model request

After sanitation, compact by message count before preparing reasoning replay, so discarded history does not incur reasoning processing. Then compact by character count after reasoning handling, measuring the actual model input. A remaining over-budget result raises the appropriate size error and emits the existing rejection KPI. The error carries only numeric sizes. The count limit must never result in a model request without the active user message. Keeping this in request override preserves checkpoints and multi-pod behavior.

## Risks / Trade-offs

- [Prior tool evidence is absent from a compacted model request] - Retain the final assistant answer and latest active tool round; durable history remains complete. A large task that needs all tool results at once still needs artifact-based processing.
- [A huge protected user message or latest tool round may reject a call] - Reject explicitly with a size error rather than fabricate context or send an incomplete request. The configured budget can later be measured in tokens.
- [Repeated full-sequence measurement can cost CPU with token accounting] - ReAct passes a 250-turn projection bound for its 500-message limit, then uses logarithmically many full-sequence measurements. Its later character measurement sees at most 500 messages. Assess the token counter's cost when one is introduced.

## Migration Plan

Deploy as a ReAct-only runtime change with no storage or schema migration. Roll back by reverting the model-input helper integration; checkpoints do not require repair.
