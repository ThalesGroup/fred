## Why

Agents with agent questions enabled still ask in plain text instead of calling `ask_user`, and they add their own "Other" choice next to the editable "Other" field managed chat already shows. A question without choices also fails the whole turn instead of reaching the person. All three were observed locally, the first two on 2026-10-10 and the third on 2026-10-08.

Tracked by [#3035](https://github.com/ThalesGroup/fred/issues/3035); folds in [#3014](https://github.com/ThalesGroup/fred/issues/3014).

## What Changes

- **One tool description.** The ReAct/Deep resolver and the Graph runtime each carry their own wording of the `ask_user` description. Both use a single description from the tool's module instead. It tells the agent to:
  - call the tool whenever it needs a decision, a preference or a missing detail from the person, rather than writing the question in its reply;
  - never add an "Other" choice, since the interface already offers an editable one.
- **Generic "Other" choices dropped.** A choice whose label is only a generic "Other" (for example "Autre", "Other", "Something else", with or without a parenthesis) is removed before the question is shown, and the question then allows free text. A specific choice such as "Other country" is kept. The choice is removed before the four-choice limit is checked, so four real choices plus "Other" are accepted.
- **No choices means free text** (#3014). A question without choices becomes a free-text question, whatever `allow_free_text` says. It no longer returns a tool error. **BREAKING for the current spec:** the "Invalid question form" scenario no longer covers that case.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-initiated-human-questions`: the requirement "An interactive agent can ask one question through a platform tool" changes as follows:
  - a question without choices is a free-text question;
  - generic "Other" choices are dropped and free text turns on;
  - the tool's guidance asks the agent to use the tool instead of asking in text;
  - the invalid-form scenario no longer covers the no-choices case.

## Impact

- **Runtime only:**
  - `libs/fred-runtime/fred_runtime/runtime_support/ask_user.py`: description, argument normalisation, free-text rule;
  - `react/react_tool_resolution.py` and `graph/graph_runtime.py`: use the shared description;
  - tests in `libs/fred-runtime/tests/`.
- **Unchanged:** the wire contract (`HumanInputRequest`), the frontend (it already renders free-text questions without choices), and the answer semantics.
- **Not addressed:** the guidance stays a prompt instruction. It makes the agent more likely to use the tool, but cannot force it.
- **Migration note:** impact `none`.
