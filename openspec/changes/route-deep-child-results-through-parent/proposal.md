## Why

Native Deep sub-agents can create user-facing files whose cards never reach the chat. A reproduced turn created ten spreadsheets without giving the user a download link. Sub-agents should contribute research and working data privately while the parent assembles any final deliverable.

## What Changes

- Mark deliverable-producing capabilities as parent-only for native Deep children. The parent keeps them and can create a final deliverable from child working data.
- Fold child sources and non-deliverable UI parts into the parent's final turn and persisted history without exposing child messages, reasoning or tool-call trace entries in the chat.
- Collect native child updates on Deep turns whether or not platform skills are enabled, while preserving normal ReAct streaming and HITL behavior.
- Add focused regression coverage for child tool availability, source/part aggregation, final history and parent-created file cards.

## Capabilities

### New Capabilities

- `deep-agent-delegation`: Defines the private child execution boundary, parent-only deliverables and aggregation of child evidence into the parent turn. The in-flight `deep-agent-runtime-baseline` change covers dispatch and baseline wiring, not delegated output ownership.

### Modified Capabilities

None.

## Impact

- Runtime: native Deep child tool composition and the existing LangGraph event collector.
- SDK and capabilities: one capability-level child-availability declaration, applied to current file-producing capabilities and documented for future ones. The child prompt and tool set must agree on availability.
- Tests and docs: runtime and capability regressions, plus the compact runtime execution contract. No new frontend API, database migration or separate publication service.
