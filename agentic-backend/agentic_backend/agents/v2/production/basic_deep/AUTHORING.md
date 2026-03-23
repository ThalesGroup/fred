# Authoring a Basic Deep Agent

A deep agent investigates a question over multiple steps — it searches,
reasons, and typically publishes a structured result. Use this shape when a
single-turn ReAct assistant is not enough.

---

## Minimal example

Create one file in `production/basic_deep/` (or `candidate/<name>/`):

```python
# my_investigator_agent.py

from agentic_backend.agents.v2.production.basic_deep.agent import BasicDeepAgentDefinition
from agentic_backend.agents.v2.production.basic_deep.prompt_loader import load_basic_deep_prompt
from agentic_backend.core.agents.v2 import ToolRefRequirement
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

class MyInvestigatorDefinition(BasicDeepAgentDefinition):
    agent_id: str = "my.investigator.v2"
    role: str = "My Investigator"
    description: str = "Investigates questions over a corpus."
    system_prompt_template: str = load_basic_deep_prompt("my_investigator_system_prompt.md")
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the corpus for evidence.",
        ),
    )
```

And the prompt in `prompts/my_investigator_system_prompt.md`:

```markdown
You are a research assistant. Investigate the user's question step by step.
Search for evidence before drawing conclusions.
Today is {today}. Answer in {response_language}.
```

---

## Adding a report output

```python
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_ARTIFACTS_PUBLISH_TEXT

class MyInvestigatorDefinition(BasicDeepAgentDefinition):
    ...
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the corpus for evidence.",
        ),
        ToolRefRequirement(
            tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
            description="Publish the final investigation report as a markdown artifact.",
        ),
    )
```

---

## Adding guardrails

Guardrails are explicit behavioral rules appended to the prompt by the runtime.
Use them to enforce grounding or uncertainty discipline.

```python
from agentic_backend.core.agents.v2 import GuardrailDefinition

class MyInvestigatorDefinition(BasicDeepAgentDefinition):
    ...
    guardrails: tuple[GuardrailDefinition, ...] = (
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground claims in evidence",
            description="Do not present unsupported claims as if they came from the corpus.",
        ),
        GuardrailDefinition(
            guardrail_id="uncertainty",
            title="State uncertainty explicitly",
            description="When evidence is missing or inconclusive, say so clearly.",
        ),
    )
```

---

## Enabling file attachments or library selection in the UI

Override `fields` to expose chat options to users:

```python
from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints

class MyInvestigatorDefinition(BasicDeepAgentDefinition):
    ...
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Core investigation instructions.",
            required=True,
            default=load_basic_deep_prompt("my_investigator_system_prompt.md"),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Allow users to attach files for analysis.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Enable library selection",
            description="Let users choose which libraries to search.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )
```

---

## Registering in the catalog

Add an entry to `agents/v2/definition_refs.py`:

```python
MY_INVESTIGATOR_DEFINITION_REF = "v2.deep.my_investigator"

_CLASS_PATH_BY_DEFINITION_REF = MappingProxyType({
    ...
    MY_INVESTIGATOR_DEFINITION_REF: (
        "agentic_backend.agents.v2.production.basic_deep.my_investigator_agent.MyInvestigatorDefinition"
    ),
})
```

---

## Prompt template variables

| Variable | Value at runtime |
|---|---|
| `{today}` | Current date |
| `{response_language}` | User's preferred language |

---

## File naming conventions

| File | Convention |
|---|---|
| Agent definition | `<name>_agent.py` |
| Prompt | `prompts/<name>_system_prompt.md` |
| Loader helper | `prompt_loader.py` (shared, already exists) |
