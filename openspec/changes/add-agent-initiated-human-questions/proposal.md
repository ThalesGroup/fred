## Why

The modern ReAct and Deep runtimes can pause for tool approval, but an agent cannot ask its user a business question and use the answer in the same turn. Issue [#2836](https://github.com/ThalesGroup/fred/issues/2836) tracks this slice of epic [#2642](https://github.com/ThalesGroup/fred/issues/2642), which settled the interaction model, and the occurrence identity foundation landed in [#2721](https://github.com/ThalesGroup/fred/pull/2721); the next slice can now add the question tool without confusing sibling pauses.

## What Changes

- Add one platform `ask_user` tool for a single choice, free text, or a choice with a comment. Its answer returns to the calling agent as a tool result so the same turn continues.
- Limit agent-authored questions to four selected choices without truncating longer calls, and show each optional choice description beneath its label in managed chat.
- Offer the tool only to an interactive conversation whose platform chat control enables it. The control starts enabled, can be switched off per conversation, and is absent from noninteractive execution.
- Let a person skip a question. The tool returns an explicit unanswered result so the agent can continue without inventing an answer.
- Show an answered question below its `ask_user` tool line immediately after resume; list the offered choices and highlight the selection in the tool drawer.
- Prove that ReAct and Deep share the same tool behavior and that multiple questions in one turn retain their distinct occurrence identities. Align Graph `choice_step()` with the enriched response shape while preserving its existing callers.

The shared HITL card redesign and free-text comments on the tool approval gate remain the next slice of the epic. Pause expiry and recovery remain separate lifecycle work.

## Capabilities

### New Capabilities

- `agent-initiated-human-questions`: interactive agent questions, answer delivery, skip behavior, and availability controls. The existing `human-in-the-loop` change owns generic pause identity and history pairing.

### Modified Capabilities

None.

## Impact

- `fred-sdk`: `RuntimeContext` and Graph `choice_step()` response handling.
- `fred-runtime`: a pure question tool, conditional ReAct/Deep tool binding, HITL resume parsing, and focused integration tests.
- Control plane: a platform-owned `ask_user_toggle` chat control in execution preparation.
- Frontend: composer state, runtime context transport, the skip action on the existing HITL prompt, and generated API clients.
- Contracts and docs: runtime and product contract amendments, frontend UX record, and an operator migration note. No database migration is expected.
