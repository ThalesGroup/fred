# fred-sdk

`fred-sdk` is the authoring library for Fred agents.  
It provides everything needed to define agents, tools, workflows, and multi-agent
compositions — with no dependency on any running platform service.

---

## Where `fred-sdk` fits

```
fred-core          Pure utilities — model factories, embeddings, logging
     │
fred-sdk           Execution engine + authoring surface  ← this package
     │              ReAct, Graph, Team, Deep agent types
     │              Tool authoring, HITL, MCP references
     │
fred-runtime       Platform adapters + pod factory
                    SQL checkpointer, LLM routing, FastAPI app factory
```

Agent logic belongs in `fred-sdk`.  
Infrastructure wiring (DB, MCP server, Keycloak, object store) belongs in `fred-runtime`.  
`fred-sdk` must stay importable on a bare laptop with no services running.

---

## Installation

```bash
pip install fred-sdk
```

Requires Python 3.12.

---

## Agent types

### ReAct agent

Tool-calling assistant backed by a ReAct loop. The most common agent type.

```python
from fred_sdk import ReActAgent, tool, ToolContext, ToolOutput

class WeatherAgent(ReActAgent):
    agent_id = "my.weather.agent"
    role = "Weather assistant"
    description = "Answers weather questions using the get_weather tool."
    system_prompt_template = "You are a helpful weather assistant."

    @tool("Get current weather for a city")
    async def get_weather(self, city: str, ctx: ToolContext) -> ToolOutput:
        # call external API here
        return ToolOutput.text(f"It is sunny in {city}.")
```

---

### Graph agent

Deterministic workflow with typed state. Nodes are Python functions; edges and
conditional routes are declared in `GraphWorkflow`.

```python
from fred_sdk import GraphAgent, GraphWorkflow, typed_node, StepResult
from pydantic import BaseModel

class MyState(BaseModel):
    message: str = ""
    result: str = ""

@typed_node(MyState)
async def process(state: MyState, ctx) -> StepResult:
    return StepResult(update={"result": f"processed: {state.message}"})

class MyGraphAgent(GraphAgent):
    agent_id = "my.graph.agent"
    role = "Processing pipeline"
    description = "Runs a deterministic processing workflow."
    state_schema = MyState
    workflow = GraphWorkflow(
        entry="process",
        nodes={"process": process},
    )
```

Graph workflow primitives available from `fred_sdk`:

| Primitive               | What it does                                                  |
| ----------------------- | ------------------------------------------------------------- |
| `typed_node`            | Decorator — turns a function into a typed graph node          |
| `GraphWorkflow`         | Declares nodes, edges, and conditional routes                 |
| `choice_step`           | Built-in node for HITL choice gates                           |
| `finalize_step`         | Built-in node that sets `final_text` and ends the graph       |
| `intent_router_step`    | Built-in LLM-powered intent classifier node                   |
| `model_text_step`       | Built-in node that calls the LLM and stores the result        |
| `structured_model_step` | Built-in node that calls the LLM and parses structured output |
| `StepResult`            | Return type for typed nodes                                   |

---

### Team agent

Multi-agent composition. A coordinator routes or sequences work across members.

```python
from fred_sdk import TeamAgent, AgentSpec

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
| ------------ | ----------------------------------------------------------------------------------- |
| `sequential` | Members run in order; each is an inline LLM call                                    |
| `dynamic`    | A coordinator LLM decides who runs next after each member                           |
| `route`      | A coordinator LLM picks exactly one registered agent and delegates the full request |

Child agents used as `agent_ref` targets should set `public = False` so they are
not exposed as top-level models in Open WebUI or other OpenAI-compatible frontends.

---

### Deep agent

Extended ReAct variant with a built-in planning step. Inherits the full ReAct
authoring surface; the planning engine is wired by the runtime.

```python
from fred_sdk import DeepAgentDefinition

class MyDeepAgent(DeepAgentDefinition):
    agent_id = "my.deep.agent"
    role = "Deep research assistant"
    description = "Plans and executes multi-step research tasks."
    ...
```

---

## Tool authoring

Tools are `async` methods decorated with `@tool` on a `ReActAgent` subclass.

```python
from fred_sdk import tool, ToolContext, ToolOutput, ToolInvocationError

@tool("Search internal documents for a query")
async def search_docs(self, query: str, ctx: ToolContext) -> ToolOutput:
    token = ctx.access_token          # bearer token from the request
    user_id = ctx.user_id             # current user
    results = await my_search_api(query, token=token)
    if not results:
        raise ToolInvocationError("No documents found.")
    return ToolOutput.text("\n".join(results))
```

`ToolContext` gives the tool access to the runtime context: `user_id`, `team_id`,
`session_id`, `language`, `access_token`, and `invoke_agent()` for sub-agent calls.

---

## Human-in-the-loop (HITL)

Pause a graph at a node and wait for user input. Use `choice_step` for menu-driven
flows or emit `HumanInputRequest` directly for free-text prompts.

```python
from fred_sdk import choice_step, HumanChoiceOption

approve_step = choice_step(
    title="Confirm transfer",
    question="Do you want to proceed with this bank transfer?",
    choices=[
        HumanChoiceOption(id="confirm", label="Yes, confirm"),
        HumanChoiceOption(id="cancel",  label="No, cancel"),
    ],
    routes={"confirm": "execute", "cancel": "abort"},
)
```

---

## MCP server references

Declare which MCP servers an agent needs. The runtime wires the actual connection.

```python
from fred_sdk import MCPServerRef, MCP_SERVER_KNOWLEDGE_FLOW_CORPUS

class MyRagAgent(ReActAgent):
    agent_id = "my.rag.agent"
    ...
    default_mcp_servers = (MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,)
```

Built-in MCP server constants:

| Constant                                   | Connects to                   |
| ------------------------------------------ | ----------------------------- |
| `MCP_SERVER_KNOWLEDGE_FLOW_CORPUS`         | Document search and retrieval |
| `MCP_SERVER_KNOWLEDGE_FLOW_FS`             | Workspace file system         |
| `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR`        | Tabular data / CSV            |
| `MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS` | OpenSearch operations         |

---

## Built-in tool references

Pre-built platform tools declared by reference (no implementation needed in the agent):

```python
from fred_sdk import TOOL_REF_KNOWLEDGE_SEARCH, TOOL_REF_ARTIFACTS_PUBLISH_TEXT

class MyAgent(ReActAgent):
    declared_tool_refs = (TOOL_REF_KNOWLEDGE_SEARCH, TOOL_REF_ARTIFACTS_PUBLISH_TEXT)
```

| Constant                                 | What it does                                  |
| ---------------------------------------- | --------------------------------------------- |
| `TOOL_REF_KNOWLEDGE_SEARCH`              | Semantic/hybrid search over indexed documents |
| `TOOL_REF_RESOURCES_FETCH_TEXT`          | Fetch document content as text                |
| `TOOL_REF_ARTIFACTS_PUBLISH_TEXT`        | Publish a text artifact to the workspace      |
| `TOOL_REF_GEO_RENDER_POINTS`             | Render geographic points on a map             |
| `TOOL_REF_TRACES_SUMMARIZE_CONVERSATION` | Summarize conversation traces                 |

---

## Running an agent

`fred-sdk` defines agents; `fred-runtime` executes them. A minimal pod:

```python
# main.py
from fred_runtime.app import create_agent_app, load_agent_pod_config
from myapp.registry import REGISTRY

config = load_agent_pod_config()
app = create_agent_app(registry=REGISTRY, config=config)
```

See [fred-runtime on PyPI](https://pypi.org/project/fred-runtime/) for the full
pod setup guide.

---

## Related packages

| Package        | PyPI                                           | Role                                                                          |
| -------------- | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| `fred-core`    | [pypi](https://pypi.org/project/fred-core/)    | Pure utilities — logging, model factories, embeddings, portable observability |
| `fred-sdk`     | [pypi](https://pypi.org/project/fred-sdk/)     | This package                                                                  |
| `fred-runtime` | [pypi](https://pypi.org/project/fred-runtime/) | Platform adapters + pod factory                                               |

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
