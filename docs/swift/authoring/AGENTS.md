# Writing a Fred Agent (v2)

Pick the shape that matches your goal, then follow the link. All shapes are
declared in `fred_sdk` (`libs/fred-sdk/`, importable as `from fred_sdk import
...`) — this doc only maps intent to shape and points at real, currently
shipping code. It does not restate `fred_sdk`'s own fields; when in doubt the
code is the spec.

`fred-sdk` defines what an agent *is*. `fred-runtime` runs it (pod factory,
checkpointer, LLM routing). See `libs/fred-sdk/README.md` for the package-level
quickstart this doc builds on.

---

## Shape 1 — Blank-slate ReAct assistant (no custom tool code)

**Use this when:** you want a conversational assistant built entirely out of
Fred's existing platform tools and MCP servers (search, filesystem, tabular
analysis…). You declare which tools it can reach and write a prompt — no
Python business logic.

```python
from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

class ItSupportDefinition(ReActAgentDefinition):
    agent_id: str = "my.it_support.v2"
    role: str = "IT Support Assistant"
    description: str = "Guides users through troubleshooting steps."
    system_prompt_template: str = "You are a helpful IT support assistant..."

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            required=False,
            default=None,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)

IT_SUPPORT_AGENT = ItSupportDefinition()
```

Register the instance in your pod's registry — no other wiring needed.

Real, currently shipping example (with the full rationale in its module
docstring — read it before writing your own):
[`apps/fred-agents/fred_agents/general_assistant.py`](../../../apps/fred-agents/fred_agents/general_assistant.py)

---

## Shape 2 — Deep research assistant

**Use this when:** you want an agent that plans before it acts — sketches a
short plan, then works through it step by step, checking intermediate
results. `DeepAgentDefinition` inherits the full ReAct authoring surface; the
planning engine is wired by the runtime (`DeepAgentRuntime` in
`fred-runtime`), not by you.

```python
from fred_sdk import MCP_SERVER_KNOWLEDGE_FLOW_CORPUS, MCPServerRef
from fred_sdk.contracts.models import DeepAgentDefinition

class MyInvestigatorDefinition(DeepAgentDefinition):
    agent_id: str = "my.investigator.v2"
    role: str = "My Investigator"
    description: str = "Investigates questions over a corpus and reports back."
    system_prompt_template: str = "You are a helpful assistant that plans before it acts..."
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
    )
```

Deep agents do not support tool-approval gates or a per-turn tool-call limit
— both raise `NotImplementedError` at runtime if set. Keep the tool surface
you declare deliberately small.

Real, currently shipping example (its module docstring explains the
filesystem-exclusion rationale, still relevant if you add file tools):
[`apps/fred-agents/fred_agents/deep_assistant.py`](../../../apps/fred-agents/fred_agents/deep_assistant.py)

---

## Shape 3 — ReAct agent with custom Python tools

**Use this when:** the platform tools are not enough and you need your own
business logic as Python functions. Subclass `ReActAgent` and decorate your
functions with `@tool`.

```python
from fred_sdk import ReActAgent, tool, ToolContext, ToolOutput

class WeatherAgent(ReActAgent):
    agent_id = "my.weather.agent"
    role = "Weather assistant"
    description = "Answers weather questions using the get_weather tool."
    system_prompt_template = "You are a helpful weather assistant."

    @tool("Get current weather for a city")
    async def get_weather(self, city: str, ctx: ToolContext) -> ToolOutput:
        # call an external API here
        return ToolOutput.text(f"It is sunny in {city}.")
```

`ToolContext` gives the tool access to the runtime context: `user_id`,
`team_id`, `session_id`, `language`, `access_token`, and `invoke_agent()` for
sub-agent calls.

> **No first-party in-tree example yet.** Every agent shipped today in
> `apps/fred-agents` builds its tool surface declaratively
> (`declared_tool_refs` / `default_mcp_servers`, Shape 1/2 above) — this
> decorator pattern is currently only exercised in `fred-runtime`'s own test
> suite (`libs/fred-runtime/tests/`). It is real, documented, supported API
> (see `libs/fred-sdk/README.md`), but if you are the first to use it for a
> real agent, expect to be the one finding the rough edges — and consider
> whether the logic you're adding belongs in a reusable
> [capability](../capabilities/AUTHORING.md) instead, if more than one agent
> might need it.

---

## Shape 4 — Graph agent (explicit workflow with HITL)

**Use this when:** the business process has multiple steps, conditional
branches, external tool calls, or requires the user to confirm an action
before it is committed. The workflow is expressed as a typed directed graph.
The SDK handles streaming, checkpointing, and human-in-the-loop interrupts.

This is the most expressive authoring shape. It is the right choice when you
need the agent's control flow to be auditable and testable independently of
any LLM call.

### Anatomy of a graph agent

A graph agent is split across three files:

| File             | Responsibility                                               |
| ---------------- | ------------------------------------------------------------ |
| `graph_state.py` | Pydantic input and state schemas                              |
| `graph_steps.py` | One function per node — pure business logic                  |
| `graph_agent.py` | Wires everything together: nodes, edges, routes, MCP servers |

### Minimal example

```python
# graph_state.py
from pydantic import BaseModel

class MyInput(BaseModel):
    message: str

class MyState(BaseModel):
    latest_user_text: str
    final_text: str = ""
```

```python
# graph_steps.py
from fred_sdk import GraphNodeContext, StepResult, typed_node

@typed_node(MyState)
async def do_work_step(state: MyState, context: GraphNodeContext) -> StepResult:
    result = await context.invoke_runtime_tool("my_tool", {"input": state.latest_user_text})
    return StepResult(state_update={"final_text": result})
```

```python
# graph_agent.py
from fred_sdk import GraphAgent, GraphWorkflow

from .graph_state import MyInput, MyState
from .graph_steps import do_work_step

class MyGraphAgent(GraphAgent):
    agent_id: str = "my.graph.v1"
    role: str = "My Graph Agent"
    description: str = "Does something step by step."

    input_schema = MyInput
    state_schema = MyState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="do_work",
        nodes={"do_work": do_work_step},
    )
```

Note the node signature — `(state, context)`, decorated with `@typed_node(YourStateModel)`
— and `StepResult`'s field: it is `state_update`, not `update`.

### Key SDK helpers

Available from `fred_sdk`:

| Helper                  | What it does                                                  |
| ------------------------ | -------------------------------------------------------------- |
| `typed_node`             | Decorator — turns a function into a typed graph node, called as `@typed_node(YourStateModel)` |
| `GraphWorkflow`          | Declares nodes, edges, conditional routes, and error routes    |
| `intent_router_step`     | LLM-based intent classification with typed routing             |
| `model_text_step`        | Single LLM call that returns text into a state field           |
| `structured_model_step`  | LLM call with a Pydantic output schema and a fallback value     |
| `choice_step`            | Pauses execution and surfaces a choice to the user (HITL)      |
| `finalize_step`          | Standard terminal node — emits `output_state_field` and ends   |

### HITL confirmation gates

`choice_step` pauses graph execution and sends an `awaiting_human` event to
the UI. When the user responds, the graph resumes at the next node. No
special infrastructure is required — checkpointing and resume are handled by
the SDK.

```python
from fred_sdk import HumanChoiceOption, StepResult, choice_step

@typed_node(MyState)
async def confirm_action_step(state: MyState, context: GraphNodeContext) -> StepResult:
    choice_id = await choice_step(
        context,
        stage="confirm_action",
        title="Confirm action",
        question="Proceed with the action?",
        choices=[
            HumanChoiceOption(id="confirmed", label="Yes, proceed"),
            HumanChoiceOption(id="cancelled", label="Cancel"),
        ],
    )
    if choice_id is None:
        return StepResult(state_update={"final_text": "No selection received."})
    ...
```

Real, currently shipping examples:
- Business-shaped workflow with real `structured_model_step` usage and a
  document picker:
  [`apps/fred-agents/fred_agents/comparison/graph_agent.py`](../../../apps/fred-agents/fred_agents/comparison/graph_agent.py)
  and its
  [`graph_steps.py`](../../../apps/fred-agents/fred_agents/comparison/graph_steps.py)
- The `choice_step` HITL snippet above is taken verbatim from
  [`apps/fred-agents/fred_agents/test_assistant/graph_steps.py`](../../../apps/fred-agents/fred_agents/test_assistant/graph_steps.py)
  (`hitl_choice_step`), a coverage-matrix agent that deliberately exercises
  every SSE event type — read it to see every event path a graph agent can
  emit, not as a business-logic template.

---

## Shape 5 — Team agent (multi-agent composition)

**Use this when:** you want a coordinator to route or sequence work across
several existing agents rather than build one big agent.

```python
from fred_sdk import AgentSpec, TeamAgent

class SupportRouter(TeamAgent):
    agent_id = "my.support.router"
    role = "Support request router"
    description = "Routes support requests to the right specialist."
    mode = "route"
    coordinator_instructions = "Pick the right specialist based on user intent."
    members = (
        AgentSpec(name="Billing", role="Billing questions", agent_ref="my.billing.agent"),
        AgentSpec(name="Technical", role="Technical issues", agent_ref="my.technical.agent"),
    )
```

Three modes:

| Mode         | Behaviour                                                                           |
| ------------ | ------------------------------------------------------------------------------------ |
| `sequential` | Members run in order; each is an inline LLM call                                     |
| `dynamic`    | A coordinator LLM decides who runs next after each member                            |
| `route`      | A coordinator LLM picks exactly one registered agent and delegates the full request  |

Child agents used as `agent_ref` targets should set `public = False` so they
are not exposed as top-level models in Open WebUI or other OpenAI-compatible
frontends.

Multi-turn memory is automatic for `TeamAgent` — see the memory section
below.

> **No in-tree instance today.** No agent in `apps/fred-agents` currently
> uses `TeamAgent`; the implementation lives in
> `libs/fred-sdk/fred_sdk/graph/authoring/team_api.py` and is otherwise
> exercised only by the SDK's own test suite. Treat the snippet above (and
> `libs/fred-sdk/README.md`) as the current source of truth.

---

## Available platform tools

Import from `fred_sdk`:

| Constant                                 | What it does                                            |
| ----------------------------------------- | -------------------------------------------------------- |
| `TOOL_REF_KNOWLEDGE_SEARCH`               | Search document libraries and return grounded snippets   |
| `TOOL_REF_ARTIFACTS_PUBLISH_TEXT`         | Publish a markdown file artifact for the user             |
| `TOOL_REF_RESOURCES_FETCH_TEXT`           | Read a config or template file                            |
| `TOOL_REF_GEO_RENDER_POINTS`              | Render geographic points on a map                         |
| `TOOL_REF_TRACES_SUMMARIZE_CONVERSATION`  | Summarise an execution trace                               |

```python
from fred_sdk import TOOL_REF_KNOWLEDGE_SEARCH, TOOL_REF_ARTIFACTS_PUBLISH_TEXT

class MyAgent(ReActAgentDefinition):
    declared_tool_refs = (TOOL_REF_KNOWLEDGE_SEARCH, TOOL_REF_ARTIFACTS_PUBLISH_TEXT)
```

## Available MCP server groups

Import from `fred_sdk`:

| Constant                                    | What it gives access to          |
| --------------------------------------------- | --------------------------------- |
| `MCP_SERVER_KNOWLEDGE_FLOW_CORPUS`            | Document search and retrieval     |
| `MCP_SERVER_KNOWLEDGE_FLOW_FS`                | User filesystem operations        |
| `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR`           | Tabular data analysis             |
| `MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS`    | OpenSearch health and monitoring  |

```python
class MyRagAgent(ReActAgentDefinition):
    default_mcp_servers = (MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),)
```

Both tables are non-exhaustive — grep `fred_sdk` for `TOOL_REF_` / `MCP_SERVER_`
constants, or read `apps/fred-agents/fred_agents/general_assistant.py` for the
current full default set.

---

## Multi-turn conversational memory

Graph agents (including `TeamAgent`) maintain state across turns via the
LangGraph checkpointer. The memory contract is opt-in: only agents whose
state inherits from `ConversationalState` get automatic carry-forward.

### How it works

1. **`ConversationalState` mixin** — adds `conversation_history: tuple[ConversationTurn, ...]`
   to any graph state class. `TeamState` already inherits it.
2. **`build_turn_state` carry-forward** — on each new turn the runtime calls
   `build_turn_state(input, binding, previous_state=<last checkpoint>)`. If the state
   includes `ConversationalState`, the previous history is carried forward automatically.
3. **`build_completed_state` hook** — called after the terminal node, before the
   checkpoint is persisted. `TeamAgent` auto-generates an override that appends a
   `ConversationTurn(user_message, agent_response, agent_name)` so the next turn sees it.
4. **Sub-agent seeding** — when a graph node calls `context.invoke_agent(...)` it can
   pass `prior_turns=state.conversation_history`. `TeamAgent` does this automatically.
   ReAct sub-agents receive the history as a leading `SystemMessage`; graph sub-agents
   receive it through `build_turn_state(invocation_turns=...)`.

### Enabling memory on a custom graph agent

```python
from pydantic import BaseModel
from fred_sdk.contracts.context import ConversationTurn, ConversationalState

class MyState(ConversationalState, BaseModel):
    user_message: str
    result: str = ""
```

That is all. `build_turn_state` will carry `conversation_history` forward on every
subsequent turn. Override `build_completed_state` to append the completed exchange:

```python
class MyAgent(GraphAgent):
    ...

    def build_completed_state(self, state: MyState) -> MyState:
        turn = ConversationTurn(
            user_message=state.user_message,
            agent_response=state.result,
        )
        return state.model_copy(
            update={"conversation_history": state.conversation_history + (turn,)}
        )
```

### Depth limit

`GraphAgentDefinition.conversation_history_max_turns` (default `20`) caps the number
of turns carried forward. Oldest turns are dropped first. Override as a `ClassVar` on
your agent class to change the limit.

### TeamAgent — fully automatic

`TeamAgent` subclasses get memory for free:

- `TeamState` already inherits `ConversationalState`
- `build_completed_state` is auto-generated in `__pydantic_init_subclass__`
- All coordinator and member prompts receive the history block when non-empty
- `_make_agent_invoke_step` passes `state.conversation_history` as `prior_turns`
  to every routed sub-agent

No author action is required.

---

## Where does my agent live?

There is no `candidate/production/samples` folder convention any more — that
belonged to the retired `agentic-backend` service. The real split today is:

| You are…                                                              | Your agent lives in…                                                                                            |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Adding one of Fred's own default agents                                  | `apps/fred-agents/fred_agents/<agent_name>/`, registered in `apps/fred-agents/fred_agents/registry.py`         |
| A third-party team bringing your own agent to a Fred deployment          | Your own independent pod built on `fred-sdk` + `fred-runtime`, in your own repository — see [`docs/swift/platform/FORKING_GUIDE.md`](../platform/FORKING_GUIDE.md) ("Current architecture (2.x) — independent agent pods") and the registration mechanics in [`docs/swift/platform/PLATFORM_RUNTIME_MAP.md`](../platform/PLATFORM_RUNTIME_MAP.md) §5.1 (`platform.runtime_catalog_sources`). Reference implementation: [fred-samples](https://github.com/ThalesGroup/fred-samples). |
| Adding one modular, cross-agent-reusable feature (not owned by one agent) | Not a new agent at all — a [capability](../capabilities/AUTHORING.md) (`AgentCapability` in `fred_sdk`)          |

If you are unsure whether what you're building is "an agent" or "a
capability": a capability is a feature multiple agents can attach (e.g.
document search); an agent is the thing a user talks to.
