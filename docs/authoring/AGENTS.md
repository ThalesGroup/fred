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

---

## Shape 4 — Graph agent (explicit workflow with HITL)

**Use this when:** the business process has multiple steps, conditional branches,
external tool calls, or requires the user to confirm an action before it is
committed. The workflow is expressed as a typed directed graph. The SDK handles
streaming, checkpointing, and human-in-the-loop interrupts.

This is the most expressive authoring shape. It is the right choice when you
need the agent's control flow to be auditable and testable independently of any
LLM call.

### Anatomy of a graph agent

A graph agent is split across three files:

| File | Responsibility |
|---|---|
| `graph_state.py` | Pydantic input and state schemas |
| `graph_steps.py` | One function per node — pure business logic |
| `graph_agent.py` | Wires everything together: nodes, edges, routes, MCP servers |

### Minimal example

```python
# graph_state.py
from pydantic import BaseModel

class MyInput(BaseModel):
    message: str

class MyState(BaseModel):
    latest_user_text: str
    result: str | None = None
```

```python
# graph_steps.py
from agentic_backend.core.agents.v2.graph.authoring import (
    StepResult, typed_node, model_text_step, intent_router_step, finalize_step,
)
from agentic_backend.core.agents.v2 import GraphNodeContext, GraphNodeResult

@typed_node
async def classify_step(ctx: GraphNodeContext, state: MyState) -> StepResult:
    # Use intent_router_step for LLM-based branching
    return await intent_router_step(ctx, state, ...)

@typed_node
async def do_work_step(ctx: GraphNodeContext, state: MyState) -> StepResult:
    # Call an MCP tool, run business logic, update state
    result = await ctx.invoke_runtime_tool("my_tool", {"input": state.latest_user_text})
    return StepResult(route_key="done", state_update={"result": result})
```

```python
# graph_agent.py
from agentic_backend.core.agents.v2.graph.authoring import GraphAgent, GraphWorkflow
from agentic_backend.core.agents.agent_spec import MCPServerRef

class MyGraphAgent(GraphAgent):
    agent_id: str = "my.graph.v1"
    role: str = "My Graph Agent"
    description: str = "Does something step by step."

    input_schema = MyInput
    state_schema = MyState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "result"

    workflow = GraphWorkflow(
        entry="classify",
        nodes={
            "classify": classify_step,
            "do_work": do_work_step,
            "finalize": finalize_step,
        },
        edges={"do_work": "finalize"},
        routes={
            "classify": {"work": "do_work", "conversational": "finalize"},
        },
    )
```

### Key SDK helpers

| Helper | What it does |
|---|---|
| `intent_router_step` | LLM-based intent classification with typed routing |
| `model_text_step` | Single LLM call that returns text into a state field |
| `structured_model_step` | LLM call with a Pydantic output schema |
| `choice_step` | Pauses execution and surfaces a choice to the user (HITL) |
| `finalize_step` | Standard terminal node — emits `output_state_field` and ends |

### HITL confirmation gates

`choice_step` pauses graph execution and sends an `awaiting_human` event to the
UI. When the user responds, the graph resumes at the next node. No special
infrastructure is required — checkpointing and resume are handled by the SDK.

```python
@typed_node
async def confirm_action_step(ctx: GraphNodeContext, state: MyState) -> StepResult:
    return await choice_step(
        ctx,
        question="Proceed with the action?",
        choices=[
            HumanChoiceOption(id="confirmed", label="Yes, proceed"),
            HumanChoiceOption(id="cancelled", label="Cancel"),
        ],
    )
```

### Complete working sample

The **bank transfer sample** is a full graph agent with two MCP servers, two HITL
confirmation gates, KYC and risk validation steps, and conditional routing at
every stage. Read it before writing your first graph agent.

- [`agentic_backend/agents/v2/samples/bank_transfer/graph_agent.py`](../agentic-backend/agentic_backend/agents/v2/samples/bank_transfer/graph_agent.py) — workflow wiring
- [`agentic_backend/agents/v2/samples/bank_transfer/graph_steps.py`](../agentic-backend/agentic_backend/agents/v2/samples/bank_transfer/graph_steps.py) — all step implementations
- [`agentic_backend/agents/v2/samples/bank_transfer/graph_state.py`](../agentic-backend/agentic_backend/agents/v2/samples/bank_transfer/graph_state.py) — state schema

---

## Where does my file go?

| Stage | Folder |
|---|---|
| Exploring an idea | `candidate/<my_agent>/` |
| Ready for real use | `production/<my_agent>/` |
| Shared reusable sample | `samples/` |
