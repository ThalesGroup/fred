# Design

## Context

Deep assembles its own middleware list and misses ReAct's request-only hygiene. The approved source is uncommitted POC code; existing execution and approval contracts remain authoritative.

## Goals / Non-Goals

Reuse shared sanitation in the parent model path and preserve checkpoint history. Native-child assembly, filesystem backends, context-compaction redesign, and custom delegation are excluded by the extraction agreement.

## Decisions

Place `CheckpointHygieneMiddleware` first in the Deep frame so capability and retry wrappers receive the prepared request once. Use `max_history_messages=None` and the existing ReAct character budget; the source POC's omission of a character cap is not a compaction solution. Reuse `strip_message_names` with copies only for named messages, leaving unnamed objects untouched. Run it before reasoning conversion and size budgeting. Preserve tool IDs and metadata for pairing and output collection.

Verify an actual compiled parent graph and OpenAI-compatible provider payload serialization, the path used by the reported Mistral gateway. Checking only `name is None` would miss serializer behavior. Existing ReAct and HITL suites guard shared behavior.

## Risks / Trade-offs

The character cap can still reject an oversized open turn; deferred compaction work must address that separately. Sanitization walks messages once more but adds no I/O or shared state. Native children do not inherit parent middleware automatically and require the next layer before full issue acceptance.
