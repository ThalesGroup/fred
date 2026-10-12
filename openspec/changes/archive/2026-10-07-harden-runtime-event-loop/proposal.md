## Why

Issue #2988's local audit reproduced event-loop starvation that can delay sibling LLM reads and trigger the chunk watchdog even with data ready on the socket. Correct the measured Fred hazards without changing model execution policy or claiming production attribution.

## What Changes

- Keep MinIO/GCS listing conversion in the existing worker and remove redundant directory scans.
- Execute supported synchronous SDK-authored tool handlers outside the event loop, preserving asynchronous handlers and context.
- Resolve the LangChain tool-argument fragment parsing hotspot only through a small, behavior-preserving integration; do not copy the streaming loop or parser.
- Keep console/audit transport unchanged: normal INFO logging is per-call, no production backpressure has been measured, and durable-audit overflow policy is outside this correction.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `llm-call-observability`: preserve progress of concurrent model calls during shared runtime work and verify local starvation separately from upstream silence.

## Impact

fred-core filesystem/model integration, fred-sdk authored tools, offline regression tests, existing operational guidance. Track in #2988 on the existing branch. Developer requested implementation and narrowly scoped local commits; no additional push or PR publication until explicitly agreed after validation. The log-transport risk remains documented, not represented as fixed.
