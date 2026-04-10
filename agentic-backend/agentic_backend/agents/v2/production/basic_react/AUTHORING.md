# Authoring a Basic ReAct Agent

Two patterns exist. Pick the one that matches your goal.

---

## Pattern A — Profile (most common)

**Use this when:** you want a new assistant option that users can select from
the *Starting Profile* dropdown when configuring a `BasicReActDefinition`.

### What to create

1. A Python file in `profiles/` — e.g. `profiles/it_support.py`
2. A Markdown prompt in `prompts/` — e.g. `prompts/basic_react_it_support_system_prompt.md`

The registry picks up your profile automatically. No other file needs to change.

### Minimal example

```python
# profiles/it_support.py

from ..profile_model import ReActProfile
from ..profile_prompt_loader import load_basic_react_prompt

IT_SUPPORT_PROFILE = ReActProfile(
    profile_id="it_support",
    title="IT Support",
    description="Helps users with common IT issues.",
    role="IT Support Assistant",
    agent_description="Guides users through troubleshooting steps for IT problems.",
    system_prompt_template=load_basic_react_prompt("basic_react_it_support_system_prompt.md"),
)
```

That's it. The profile now appears in the dropdown.

### Adding tools

```python
from agentic_backend.core.agents.v2 import ToolRefRequirement
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

IT_SUPPORT_PROFILE = ReActProfile(
    ...
    declared_tool_refs=(
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the IT knowledge base for known fixes.",
        ),
    ),
)
```

### Adding guardrails

```python
from agentic_backend.core.agents.v2 import GuardrailDefinition

IT_SUPPORT_PROFILE = ReActProfile(
    ...
    guardrails=(
        GuardrailDefinition(
            guardrail_id="scope",
            title="Stay in scope",
            description="Only answer IT-related questions. Redirect others politely.",
        ),
    ),
)
```

### Requiring human approval before sensitive tool calls

```python
IT_SUPPORT_PROFILE = ReActProfile(
    ...
    enable_tool_approval=True,
    approval_required_tools=("reset_user_password", "wipe_device"),
)
```

### Enabling file attachments or library selection in the UI

```python
from agentic_backend.common.structures import AgentChatOptions

IT_SUPPORT_PROFILE = ReActProfile(
    ...
    chat_options=AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
    ),
)
```

---

## Pattern B — Preset class

**Use this when:** you need a *catalog-registered* agent with a stable
`agent_id` (e.g. `"it.support.v2"`). A preset class is a subclass of
`BasicReActDefinition` that pins one profile as its permanent default.

You still write a profile first (Pattern A). The preset class just wraps it
with a fixed identity.

### What to create

1. A profile in `profiles/` (Pattern A above)
2. A preset file at the `basic_react/` root — e.g. `it_support_agent.py`
3. Register it in `agents/v2/definition_refs.py` and export it from
   `agents/v2/__init__.py`

### Minimal example

```python
# it_support_agent.py

from pydantic import Field
from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.v2 import GuardrailDefinition, ToolRefRequirement

from .agent import BasicReActDefinition
from .profiles.it_support import IT_SUPPORT_PROFILE


class ItSupportV2Definition(BasicReActDefinition):
    agent_id: str = "it.support.v2"
    react_profile_id: str = IT_SUPPORT_PROFILE.profile_id
    role: str = IT_SUPPORT_PROFILE.role
    description: str = IT_SUPPORT_PROFILE.agent_description
    tags: tuple[str, ...] = IT_SUPPORT_PROFILE.tags
    system_prompt_template: str = Field(
        default=IT_SUPPORT_PROFILE.system_prompt_template, min_length=1
    )
    fields: tuple[FieldSpec, ...] = tuple(
        field.model_copy(update={"default": IT_SUPPORT_PROFILE.profile_id})
        if field.key == "react_profile_id"
        else field.model_copy(deep=True)
        for field in BasicReActDefinition().fields
    )
    declared_tool_refs: tuple[ToolRefRequirement, ...] = IT_SUPPORT_PROFILE.declared_tool_refs
    guardrails: tuple[GuardrailDefinition, ...] = IT_SUPPORT_PROFILE.guardrails
```

All business defaults live in the profile. The preset class only adds the
stable `agent_id`.

---

## Decision guide

| I want to… | Use |
|---|---|
| Add a new option to the profile dropdown | Profile only (Pattern A) |
| Register an agent in the Fred catalog | Preset class (Pattern B) |
| Change an existing assistant's prompt | Edit the profile's `.md` file |
| Add a tool to an existing assistant | Edit the profile's `declared_tool_refs` |

---

## File naming conventions

| File | Convention |
|---|---|
| Profile module | `profiles/<profile_id>.py` |
| Prompt file | `prompts/basic_react_<profile_id>_system_prompt.md` |
| Preset class | `<agent_name>_agent.py` at the `basic_react/` root |
