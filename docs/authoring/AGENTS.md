# Writing a Fred Agent (v2)

Pick the shape that matches your goal, then follow the link.

---

## Shape 1 — Profile-based assistant (no code)

**Use this when:** you want a conversational assistant that uses existing Fred
tools (search, filesystem, logs…). You write a prompt and declare which tools
it can call. No Python logic needed.

```python
# profiles/it_support.py
from agentic_backend.agents.v2.production.basic_react.profile_model import ReActProfile
from agentic_backend.agents.v2.production.basic_react.profile_prompt_loader import load_basic_react_prompt
from agentic_backend.core.agents.v2 import ToolRefRequirement
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH

IT_SUPPORT_PROFILE = ReActProfile(
    profile_id="it_support",
    title="IT Support",
    description="Helps users with common IT issues.",
    role="IT Support Assistant",
    agent_description="Guides users through troubleshooting steps.",
    system_prompt_template=load_basic_react_prompt("basic_react_it_support_system_prompt.md"),
    declared_tool_refs=(
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search the IT knowledge base.",
        ),
    ),
)
```

Drop the file in `production/basic_react/profiles/`. Done — auto-discovered,
no registration needed.

Full guide: [`agentic_backend/agents/v2/production/basic_react/AUTHORING.md`](../agentic-backend/agentic_backend/agents/v2/production/basic_react/AUTHORING.md)

---

## Shape 2 — Deep research assistant

**Use this when:** you want an agent that investigates a problem in multiple
steps — searches, synthesises, publishes a report. Extend
`BasicDeepAgentDefinition` and declare which tools it can use.

```python
# my_investigator_agent.py
from agentic_backend.agents.v2.production.basic_deep.agent import BasicDeepAgentDefinition
from agentic_backend.agents.v2.production.basic_deep.prompt_loader import load_basic_deep_prompt
from agentic_backend.core.agents.v2 import GuardrailDefinition, ToolRefRequirement
from agentic_backend.core.agents.v2.support.builtins import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
)

class MyInvestigatorDefinition(BasicDeepAgentDefinition):
    agent_id: str = "my.investigator.v2"
    role: str = "My Investigator"
    description: str = "Investigates questions over a corpus and publishes a report."
    system_prompt_template: str = load_basic_deep_prompt("my_investigator_system_prompt.md")
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(tool_ref=TOOL_REF_KNOWLEDGE_SEARCH, description="Search the corpus."),
        ToolRefRequirement(tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT, description="Publish the report."),
    )
    guardrails: tuple[GuardrailDefinition, ...] = (
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground claims in evidence",
            description="Do not present unsupported claims as if they came from the corpus.",
        ),
    )
```

Full guide: [`agentic_backend/agents/v2/production/basic_deep/AUTHORING.md`](../agentic-backend/agentic_backend/agents/v2/production/basic_deep/AUTHORING.md)

---

## Shape 3 — Agent with custom Python tools

**Use this when:** the platform tools are not enough and you need to write your
own business logic as Python functions. Subclass `ReActAgent` and decorate your
functions with `@tool`.

```python
from agentic_backend.core.agents.v2.authoring import ReActAgent, ToolContext, ToolOutput, tool

@tool(tool_ref="my.tool.ref", description="Compute something custom.")
def my_tool(ctx: ToolContext, value: str) -> ToolOutput:
    return ctx.text(f"Result for {value}")

class MyAgentDefinition(ReActAgent):
    agent_id: str = "my.agent.v2"
    role: str = "My Agent"
    description: str = "Does something custom."
    tools = (my_tool,)
    system_prompt_template: str = "You are a helpful assistant. Use my_tool when asked."
```

A working sample lives in [`agentic_backend/agents/v2/samples/tutorial_tools/agent.py`](../agentic-backend/agentic_backend/agents/v2/samples/tutorial_tools/agent.py).

---

## Available platform tools

| Constant | What it does |
|---|---|
| `TOOL_REF_KNOWLEDGE_SEARCH` | Search document libraries and return grounded snippets |
| `TOOL_REF_ARTIFACTS_PUBLISH_TEXT` | Publish a markdown file artifact for the user |
| `TOOL_REF_RESOURCES_FETCH_TEXT` | Read a config or template file |
| `TOOL_REF_LOGS_QUERY` | Query backend logs for troubleshooting |
| `TOOL_REF_TRACES_SUMMARIZE_CONVERSATION` | Summarise an execution trace |

Import them from `agentic_backend.core.agents.v2.support.builtins`.

## Available MCP server groups

| Constant | What it gives access to |
|---|---|
| `MCP_SERVER_KNOWLEDGE_FLOW_FS` | User filesystem operations |
| `MCP_SERVER_KNOWLEDGE_FLOW_CORPUS` | Corpus build and management |
| `MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS` | OpenSearch health and monitoring |
| `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR` | Tabular data analysis |

Import them from `agentic_backend.core.agents.v2` and pass as `MCPServerRef(id=...)`.

---

## Where does my file go?

| Stage | Folder |
|---|---|
| Exploring an idea | `candidate/<my_agent>/` |
| Ready for real use | `production/<my_agent>/` |
| Shared reusable sample | `samples/` |
