## Context

`ask_user` lives in `fred_runtime/runtime_support/ask_user.py`: `AskUserArgs` is both the argument schema the model sees and the validator, and `ask_user()` builds the `HumanInputRequest`. Two runtimes expose it:
- the ReAct/Deep resolver (`react/react_tool_resolution.py`);
- the Graph runtime (`graph/graph_runtime.py`).

Each one writes its own description string. The two strings are close but not identical, and neither asks the agent to prefer the tool over a question written in text.

Today `free_text` is `allow_free_text or len(choices) >= 2`, and a call with neither choices nor `allow_free_text` raises `ask_user requires choices or free text`. #3014 shows how that error then costs the person the whole turn.

Evidence of the two other problems is in session 34fca628 (local, 2026-10-10):
- the agent first wrote the question as Markdown;
- it then called the tool with `{"id": "4", "label": "Autre"}` among its choices, and managed chat added its own "Other" field.

## Goals / Non-Goals

**Goals:**
- One description string, owned by the tool's module.
- Accept a question with no choices, or with a generic "Other" choice, as a valid free-text question instead of rejecting it.

**Non-Goals:**
- Forcing tool use. A prompt instruction can make it more likely, not guaranteed. A system-prompt addition was considered and left out: the tool description reaches every runtime the same way and is the smaller change.
- The optional part of #3014, a model-actionable message for argument errors. Once the no-choices case is accepted, the remaining errors (duplicate ids, more than four choices) are rare. The "tool error owns the final answer" policy in `react_runtime.py` is unchanged.
- Frontend changes. A free-text question with no choices already renders.

## Decisions

1. **Shared description constant.** `ASK_USER_DESCRIPTION` in `ask_user.py`, imported by both runtimes. The duplicated strings are deleted. The `choices` field description also says not to include "Other", because some models read field descriptions more closely than the tool description.
2. **Normalise generic "Other" choices in a `mode="before"` validator on `AskUserArgs`.**
   - Running before field validation lets the four-choice limit count only the real choices. A model that sends four choices plus "Other" therefore gets through.
   - The validator does not change the JSON schema the model sees, so `maxItems: 4` is still advertised.
   - When at least one choice is dropped, it sets `allow_free_text` to true, since the agent clearly wanted an open answer. This also keeps the open path when only one choice is left.
   - **Alternative:** reject the call with a message. Rejected, because it costs an extra model call and can still end the turn on the generic error.
   - **Alternative:** filter in the frontend. Rejected, because the agent would then receive a choice id the person can never pick, and the runtime contract would stay wrong.
3. **Matching rule.**
   - The label is normalised: casefold, accents stripped, any trailing parenthetical removed, punctuation and whitespace trimmed.
   - It is then compared to a small fixed set: `autre`, `autres`, `autre chose`, `autre reponse`, `other`, `others`, `other answer`, `something else`.
   - Matching is exact after normalisation, so "Other country" or "Autre région" are kept. The description is not considered.
   - The list stays small and bilingual, matching the two UI languages.
4. **Free-text rule.** `free_text = allow_free_text or len(choices) != 1`: zero choices or two or more choices allow text. A single choice without `allow_free_text` stays a single choice, as the "Single choice" scenario requires. The "requires choices or free text" check is deleted.

## Risks / Trade-offs

- [The model still writes the question in text] → Guidance only; observe it again after the change. If it persists, a system-prompt line injected when agent questions are on is the next step, as its own change.
- [A legitimate choice labelled exactly "Other" is dropped] → The person still has the editable "Other" field, so no answer becomes impossible. The agent receives `text` instead of that choice's id.
- [Archive order] → Three in-flight changes MODIFY this same requirement: `add-agent-initiated-human-questions`, `refine-agent-question-answers` and `refresh-hitl-card-visuals`. This delta is written from the current spec on `swift`. Whichever change archives after another must re-apply its edits onto the then-current requirement text. The edits do not overlap: this change touches the requirement text and the invalid-form scenario and adds three scenarios, while the visual refresh touches managed-chat scenarios.
