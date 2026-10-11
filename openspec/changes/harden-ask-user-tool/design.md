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
- Accept a question with no choices as a valid free-text question instead of rejecting it.

**Non-Goals:**
- Forcing tool use. A prompt instruction can make it more likely, not guaranteed. A system-prompt addition was considered and left out: the tool description reaches every runtime the same way and is the smaller change.
- The optional part of #3014, a model-actionable message for argument errors. Once the no-choices case is accepted, the remaining errors (duplicate ids, more than four choices) are rare. The "tool error owns the final answer" policy in `react_runtime.py` is unchanged.
- Frontend changes. A free-text question with no choices already renders.

## Decisions

1. **Shared description constant.** `ASK_USER_DESCRIPTION` in `ask_user.py`, imported by both runtimes. The duplicated strings are deleted. The `choices` field description also says not to include "Other", because some models read field descriptions more closely than the tool description.
2. **No runtime filtering of "Other" choices.** The tool description (decision 1) is the only guard; a choice is shown as the agent gives it. A `mode="before"` validator matching a hardcoded list of generic labels was implemented, then removed at review: a word list is brittle and language-bound, and deleting it is the smaller change.
3. **Free-text rule.** `free_text = allow_free_text or len(choices) != 1`: zero choices or two or more choices allow text. A single choice without `allow_free_text` stays a single choice, as the "Single choice" scenario requires. The "requires choices or free text" check is deleted.

## Risks / Trade-offs

- [The model still writes the question in text] → Guidance only; observe it again after the change. If it persists, a system-prompt line injected when agent questions are on is the next step, as its own change.
- [The model still adds an "Other" choice] → The card then shows it next to the editable "Other" row: redundant, not blocking. Observed absent in the manual check after the description change.
- [Archive order] → Three in-flight changes MODIFY this same requirement: `add-agent-initiated-human-questions`, `refine-agent-question-answers` and `refresh-hitl-card-visuals`. This delta is written from the current spec on `swift`. Whichever change archives after another must re-apply its edits onto the then-current requirement text. The edits do not overlap: this change touches the requirement text and the invalid-form scenario and adds two scenarios, while the visual refresh touches managed-chat scenarios.
