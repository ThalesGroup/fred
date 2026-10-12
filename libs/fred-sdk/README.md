# fred-sdk

`fred-sdk` is the authoring library for what you add to Fred: **agents** (ReAct,
Graph, Team, Deep), their tools, and **Knowledge Bases** that keep a team's
library in sync with an outside source. It depends on no running platform
service and stays importable on a bare laptop.

---

## Where `fred-sdk` fits

```
fred-pod                    configuration, identity, naming
└── fred-sdk                authoring contracts            ← this package
    ├── [knowledge-base]    + the workflow engine          → a Knowledge Base pod
    └── [agents]            + fred-core, langchain, langgraph
        └── fred-runtime    execution, MCP, model routing  → an agent pod
```

Agent and Knowledge Base logic belongs here. Infrastructure wiring (database,
MCP connections, Keycloak, object storage) belongs in `fred-runtime`. What a
pod is, and which package each kind installs:
[fred-pod](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-pod).

---

## Installation

```bash
pip install fred-sdk[agents]          # agent authoring
pip install fred-sdk[knowledge-base]  # a Knowledge Base pod
```

The base install carries only configuration, identity and the plain contract
models, so a Knowledge Base pod never pulls in the agents platform; `[agents]`
adds `fred-core`, langchain and langgraph on top.

Requires Python 3.12.

---

## Agent types

### ReAct agent

Tool-calling assistant backed by a ReAct loop. The most common agent type.

```python
from fred_sdk import ReActAgent, ToolContext, ToolOutput, tool

@tool("acme.weather.current", description="Get the current weather for a city.")
async def get_weather(context: ToolContext, city: str) -> ToolOutput:
    # call an external API here
    return context.text(f"It is sunny in {city}.")

class WeatherAgent(ReActAgent):
    agent_id: str = "acme.weather.assistant"
    role: str = "Weather assistant"
    description: str = "Answers weather questions with the get_weather tool."
    system_prompt_template: str = "You are a helpful weather assistant."
    tools = (get_weather,)

WEATHER_AGENT = WeatherAgent()  # what a pod's registry holds
```

`agent_id` is a contributed name: a dotted name under a prefix you own.

---

### Graph agent

Deterministic workflow with typed state. Nodes are Python functions; edges and
conditional routes are declared in `GraphWorkflow`.

```python
from pydantic import BaseModel
from fred_sdk import GraphAgent, GraphNodeContext, GraphWorkflow, StepResult, typed_node

class EchoInput(BaseModel):
    message: str

class EchoState(BaseModel):
    latest_user_text: str = ""
    final_text: str | None = None      # the answer the user sees

@typed_node(EchoState)
async def echo(state: EchoState, context: GraphNodeContext) -> StepResult:
    return StepResult(state_update={"final_text": f"You said: {state.latest_user_text}"})

class EchoAgent(GraphAgent):
    agent_id: str = "acme.samples.echo"
    role: str = "Echo"
    description: str = "Repeats the message back, in one graph step."
    input_schema = EchoInput
    state_schema = EchoState
    input_to_state = {"message": "latest_user_text"}
    workflow = GraphWorkflow(entry="echo", nodes={"echo": echo})
```

A node returns a `StepResult`; `route_key` picks the next node among the
`routes` declared in `GraphWorkflow`, and `edges` chain nodes unconditionally.

Graph workflow primitives available from `fred_sdk`:

| Primitive               | What it does                                                        |
| ----------------------- | ------------------------------------------------------------------- |
| `typed_node`            | Decorator — turns a function into a typed graph node                |
| `GraphWorkflow`         | Declares nodes, edges, and conditional routes                       |
| `StepResult`            | What a node returns: a state update and an optional `route_key`     |

The `*_step` functions are helpers you call **inside** a node, with its
`context`:

| Helper                  | What it does                                                        |
| ----------------------- | ------------------------------------------------------------------- |
| `model_text_step`       | Calls the model and returns its text                                |
| `structured_model_step` | Calls the model and returns a parsed Pydantic object                |
| `intent_router_step`    | Classifies the request and returns a `StepResult` routed on it      |
| `choice_step`           | Pauses for a human choice and returns the chosen id (HITL)          |
| `finalize_step`         | Builds the node result that ends the graph with its final text      |

---

### Team agent

Multi-agent composition. A coordinator routes or sequences work across members.

```python
from fred_sdk import TeamAgent, AgentSpec

class SupportRouter(TeamAgent):
    agent_id: str = "acme.support.router"
    role: str = "Support request router"
    description: str = "Routes support requests to the right specialist."
    mode = "route"
    coordinator_instructions = "Pick the right specialist based on user intent."
    members = (
        AgentSpec(name="Billing", role="Billing questions", agent_ref="acme.billing.agent"),
        AgentSpec(name="Technical", role="Technical issues", agent_ref="acme.technical.agent"),
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
from fred_sdk import DeepAgentDefinition, ReActPolicy

class ResearchAgent(DeepAgentDefinition):
    agent_id: str = "acme.research.deep"
    role: str = "Research assistant"
    description: str = "Plans multi-step research before answering."
    system_prompt_template: str = "Break the request into steps, then answer."

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)
```

---

## Tool authoring

A tool is a module-level `async` function decorated with `@tool` and listed in
the agent's `tools = (...)`. Its first parameter is always the `ToolContext`;
the others are its inputs, and their type annotations become the schema the
model sees.

Synchronous handlers are also supported: Fred runs them in LangChain's shared
executor with copied context variables, so blocking I/O does not stall the event
loop. Use `async def` for handlers that need the runtime event loop or async
clients. Cancellation stops awaiting a synchronous handler; it cannot terminate
its running thread or undo side effects, and Fred does not replay the call.

```python
from fred_sdk import ToolContext, ToolOutput, tool

@tool("acme.docs.search", description="Search the team's documents for a query.")
async def search_docs(context: ToolContext, query: str) -> ToolOutput:
    result = await context.invoke_tool("knowledge.search", query=query, top_k=5)
    if not result.sources:
        return context.error("No documents found.")
    return context.text(f"Found {len(result.sources)} passages.")
```

`ToolContext` is how a tool uses Fred without touching the runtime: call
other tools (`invoke_tool`), read the agent's settings (`config`), read and
write files (`read`, `write`, `ls`), and answer (`text`, `json`, `error`,
`link`). The user's identity and token stay inside the runtime.

---

## Human-in-the-loop (HITL)

A graph node pauses for the user with `choice_step`. The run is checkpointed,
and the node resumes with the chosen id once the user answers; route on it
with `route_key`.

```python
from fred_sdk import GraphNodeContext, HumanChoiceOption, StepResult, choice_step, typed_node

@typed_node(TransferState)
async def confirm_transfer(state: TransferState, context: GraphNodeContext) -> StepResult:
    choice = await choice_step(
        context,
        stage="confirm_transfer",
        title="Confirm transfer",
        question=f"Transfer {state.amount} EUR?",
        choices=[
            HumanChoiceOption(id="confirm", label="Yes, confirm"),
            HumanChoiceOption(id="cancel", label="No, cancel"),
        ],
    )
    return StepResult(route_key="confirmed" if choice == "confirm" else "cancelled")
```

The bank transfer sample in `fred-samples` has two such gates.

---

## MCP server references

Declare which capabilities or MCP servers an agent needs. The runtime wires them.

```python
from fred_sdk import MCPServerRef, ReActAgent

class DocumentAgent(ReActAgent):
    agent_id: str = "acme.docs.assistant"
    role: str = "Document assistant"
    description: str = "Answers from the team's documents."
    system_prompt_template: str = "Answer from the documents you find."
    default_mcp_servers: tuple[MCPServerRef, ...] = (MCPServerRef(id="document_access"),)
```

Built-in MCP server constants:

| Constant                                   | Connects to                   |
| ------------------------------------------ | ----------------------------- |
| `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR`        | Tabular data / CSV            |
| `MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS` | OpenSearch operations         |

---

## Built-in tool references

Pre-built platform tools declared by reference (no implementation needed in the agent):

```python
from fred_sdk import TOOL_REF_KNOWLEDGE_SEARCH, ReActAgent, ToolRefRequirement

class SearchAgent(ReActAgent):
    agent_id: str = "acme.docs.search"
    role: str = "Search assistant"
    description: str = "Finds passages in the team's documents."
    system_prompt_template: str = "Search before you answer."
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(tool_ref=TOOL_REF_KNOWLEDGE_SEARCH),
    )
```

| Constant                                 | What it does                                  |
| ---------------------------------------- | --------------------------------------------- |
| `TOOL_REF_KNOWLEDGE_SEARCH`              | Semantic/hybrid search over indexed documents |
| `TOOL_REF_GEO_RENDER_POINTS`             | Render geographic points on a map             |
| `TOOL_REF_TRACES_SUMMARIZE_CONVERSATION` | Summarize conversation traces                 |

---

## Testing your nodes offline

Graph nodes reach the model and sub-agents through two calls: `context.invoke_agent(...)`
and `context.invoke_structured_model(...)` (used by `structured_model_step`).
`fred_sdk.testing` ships `FakeGraphNodeContext`, a double covering exactly
those two, so a node's business logic can be tested without a real model or a
real sub-agent.

```python
from typing import cast
from fred_sdk import AgentInvocationResult, GraphNodeContext
from fred_sdk.testing import FakeGraphNodeContext

context = FakeGraphNodeContext(
    agent_result=AgentInvocationResult(
        agent_id="my.specialist.agent", structured={"trust": "high"}
    ),
    structured_results={"intent": "question_cloud_general"},
)
result = await my_node(state, cast(GraphNodeContext, context))

assert context.agent_calls[0]["agent_id"] == "my.specialist.agent"
```

A call you did not configure raises `AssertionError` immediately, so an
under-specified test fails loudly instead of silently returning `None` into
your node's logic.

---

## Running an agent

`fred-sdk` defines agents; `fred-runtime` executes them. A pod serves a
registry of agent instances:

```python
# main.py
from fred_runtime.app import create_agent_app, load_agent_pod_config

REGISTRY = {WEATHER_AGENT.agent_id: WEATHER_AGENT}

app = create_agent_app(registry=REGISTRY, config=load_agent_pod_config())
```

The full pod setup is in the
[fred-runtime README](https://github.com/ThalesGroup/fred/tree/swift/libs/fred-runtime),
and [fred-samples](https://github.com/fred-agent/fred-samples/tree/swift/agents)
is a working pod with several agents.

---

## Knowledge Bases — beta

`fred_sdk.knowledge_base` tells Fred where a team's documents come from and how to
keep them current: declare an identity and configuration fields, write one async
handler, call `knowledge_base_main(kb)`. Fred supplies the destination library, a
workload identity and a cadence; the handler owns discovery, replay-safe writes and
explicit retractions — Fred never infers a deletion from absence.

```python
from fred_sdk.knowledge_base import (
    DocumentPublisher, FieldSpec, KnowledgeBase, KnowledgeBaseReconciliation,
    KnowledgeBaseRunContext, KnowledgeBaseRunOutcome, KnowledgeBaseSyncResult,
    knowledge_base_main,
)

kb = KnowledgeBase(
    id="acme.notes.hello",
    version="1.0.0",
    name="Hello notes",
    description="Keeps one note in the team's library.",
    configuration_fields=[
        FieldSpec(key="greeting", type="string", title="Greeting",
                  description="Text of the note.", default="Hello"),
    ],
)

@kb.synchronize
async def synchronize(context: KnowledgeBaseRunContext) -> KnowledgeBaseSyncResult:
    text = str(context.configuration.get("greeting") or "Hello")
    async with DocumentPublisher.for_run(context) as publisher:  # this run's library
        handle = await publisher.publish(
            relative_path="hello.md", content=f"# {text}".encode(), version=text
        )
        outcome = await publisher.wait(handle.task_id)
    return KnowledgeBaseSyncResult(
        outcome=KnowledgeBaseRunOutcome.succeeded if outcome.succeeded
        else KnowledgeBaseRunOutcome.failed,
        reconciliation=KnowledgeBaseReconciliation.complete,
        discovered=1,
        created=int(handle.created),
        updated=int(not handle.created),
    )

if __name__ == "__main__":
    raise SystemExit(knowledge_base_main(kb))  # the `publish` and `run` commands
```

`reconciliation` says what the run may conclude from an absence: `complete`
(it listed the whole source, so what is gone was removed), `partial` (a bounded
or incremental pass — act only on explicit deletions) or `up_to_date` (it proved
nothing changed and wrote nothing; refused next to any write).

`DocumentPublisher.for_run(context)` opens the run's library as the pod, with
the configuration the pod started with; a pod that keeps its own store gets
`KnowledgeFlowNotConfigured` instead. It is the shortcut for writing: a write is accepted at once and
ingested by Fred afterwards, `wait` follows it to its end, and `documents()`
reads back what the library holds so a run can reconcile against it. A source
that can say what changed since a version (a Git revision) keeps that version in
Fred with `record_source_version()` and reads it back with `source_version()`.
Install `fred-sdk[knowledge-base]`. Three working Knowledge Bases live in
[fred-samples](https://github.com/fred-agent/fred-samples/tree/swift/knowledge-bases).

A Knowledge Base acts as a workload, so it needs a deployment that authenticates
and a confidential client of its own. A pod started without its client secret and
realm fails immediately, naming what it lacks. A stack running with authentication
off cannot host one — including for local development.

**Metrics and logs come with the SDK; you write no code for them.** Name the pod
with `app.runtime_id` in its `configuration.yaml` (a lowercase slug, chosen by
whoever deploys it — the pod refuses to start without one). Every run, every call
a run makes to Fred and every ingestion wait is then measured as `fred_kb_*` series labelled
`service=<runtime_id>`, served read-only on `observability.kpi.prometheus` (port
9000, loopback until bound outward), and every log line is JSON on standard
output carrying the same `service` (`observability.logs.format: text` for a
terminal). To count something of your own, use `prometheus_client` as usual: the
same endpoint serves it. Never label a series with a team, an instance or a
document. Issue totals are computed automatically before warning/error details
are limited to 50 per severity; `issue_counts` preserves these totals when a
result is serialized and reconstructed. The contract, and the questions it answers, are in
[KNOWLEDGE-BASE.md §8](https://github.com/ThalesGroup/fred/blob/swift/docs/swift/design/KNOWLEDGE-BASE.md#8-operational-metrics).

**This surface is beta: pin your `fred-sdk` version, as it may change between beta
releases.** Known limits today:

- Configuration fields are fixed once instances exist — there is no schema
  migration. Deleting a synchronized folder deletes its documents.
- Fred's UI shows nothing of a run yet: counters, summaries and issues a handler
  returns are exported as metrics only, not stored or displayed, and Fred offers
  no run history or manual trigger yet.
- A relative path is the document key, so a rename reads as a delete plus an add.
- Cadences are hourly, daily or weekly, with no immediate first run.

The label applies to Knowledge Bases only, not to this SDK's agent APIs.

---

## Related packages

| Package        | PyPI                                           | Role                                                                     |
| -------------- | ---------------------------------------------- | ------------------------------------------------------------------------ |
| `fred-pod`     | [pypi](https://pypi.org/project/fred-pod/)     | What every pod shares — configuration, identity, naming                  |
| `fred-core`    | [pypi](https://pypi.org/project/fred-core/)    | The agents platform — stores, model providers, logging, observability    |
| `fred-sdk`     | [pypi](https://pypi.org/project/fred-sdk/)     | This package                                                             |
| `fred-runtime` | [pypi](https://pypi.org/project/fred-runtime/) | Agent execution, platform adapters and the pod factory                   |

---

## License

[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
