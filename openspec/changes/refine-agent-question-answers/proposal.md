## Why

An agent can recover from an invalid `ask_user` call and pause on a valid question, yet managed chat still receives the old tool failure as the turn's final answer. Multiple-choice questions also place free text outside the choice list and can omit it entirely, leaving people without an "Other" answer.

Tracked by [#2899](https://github.com/ThalesGroup/fred/issues/2899).

## What Changes

- A turn paused for an agent question does not emit a stale tool failure as its final answer. The pause carries earlier sources, UI parts, and token usage so they survive history and resume. Failed turns that do not pause retain their safe error response.
- After an answered question, Mistral tool-call text with the existing typed marker can still route a registered `ask_user` call when its JSON question contains literal line breaks. Validate the public arguments and the full question rules with a temporary call ID before LangChain injects the real one.
- Agent questions with two or more choices always accept a text answer, regardless of the model's `allow_free_text` argument. The four-choice limit remains.
- Managed chat places a localized gray "Other" / "Autre" label beside the editable last row of the choice list and renders question Markdown. Text-only questions and tool approvals retain their existing forms.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-initiated-human-questions`: free-text availability and presentation for multiple-choice questions, and final-answer behavior while awaiting a response.

## Impact

ReAct runtime streaming and `ask_user` request construction, managed-chat HITL rendering, focused tests, runtime and UX documentation, and one migration note. The pause event gains additive metadata fields; the database schema remains unchanged.
