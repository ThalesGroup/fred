# V2 Developer Guide

This guide is only for the v2 agent stack in `agentic-backend`.

The v2 layer is an authoring layer first. You choose the service shape in Fred
terms, then the runtime delegates execution to the matching engine later, such
as the ReAct stack or the deep-agent runtime.

Start here:

**What do you want to implement, and why?**

Do not start from a runtime or a pattern.
Start from the user-facing service you need to deliver.

In v2, the default choice is:

- use a **Basic ReAct** definition when a conversational assistant with prompt tuning and declared tools is enough
- add **custom ReAct tools** only when the existing platform tools do not provide the business capability you need
- use a **Deep agent** only when Basic ReAct does not do the job and you still want a conversational assistant, not a fixed workflow
- use a **Graph agent** only when the business value depends on an explicit sequence of steps, decisions, pauses, or guarded actions

If you choose a bigger shape than needed, you will make the agent harder to review, harder to explain, and harder to maintain.

## Tool Model

Before choosing an agent shape, keep the v2 tool model simple:

- `declared_tool_refs`: exact Fred tools declared in the agent contract
- `default_mcp_servers`: MCP servers Fred should attach by default at runtime
- local Python `@tool(...)` functions: authoring sugar that Fred turns into declared tool refs for that agent

Why this matters:

- developers should declare business tool needs, not runtime plumbing
- Fred should expose one final runtime tool surface to the model, even if the tools come from different sources
- if Fred already exposes a first-class tool ref such as `knowledge.search`, prefer that over depending directly on a raw MCP server for the same business need

Use this rule:

- start with built-in Fred tool refs
- add local Python tools when one missing business action is small and agent-specific
- attach MCP servers when the needed tools live outside Fred and should be provided dynamically at runtime

## 1. Pick The Smallest Shape That Fits

Use this order.

### Start with Basic ReAct

Choose Basic ReAct when:

- the agent mainly answers in chat
- the business logic is mostly in the system prompt
- the agent may call a small set of declared tools
- there is no need to guarantee a fixed step order

Business value:

- fastest way to ship a useful assistant
- easiest shape for product owners and developers to review
- simplest tuning surface for prompts, chat options, and safety

Repository example:

- `agentic_backend/agents/v2/production/basic_react/agent.py`
- `agentic_backend/agents/v2/production/basic_react/profiles/rag_expert.py`

### Move to ReAct With Custom Tools

Choose this when:

- Basic ReAct is still the right shape
- but the existing platform tools do not expose the business action you need
- and you can express the missing capability as one or a few clear tools

Business value:

- keep the conversational runtime
- add business capability without inventing a graph
- keep tool ownership explicit and testable

Repository example:

- `agentic_backend/core/agents/v2/authoring.py`

### Move to Deep Agent Only If Basic ReAct Fails

Choose Deep only when:

- you still want a conversational assistant
- but the task needs longer multi-step investigation or planning than your Basic ReAct delivers well
- and the user does not need an explicit business workflow they can inspect node by node

Business value:

- stronger autonomous research behavior
- still keeps the assistant experience
- avoids graph complexity when the business journey is not fixed

Repository example:

- `agentic_backend/agents/v2/production/basic_deep/agent.py`
- `agentic_backend/agents/v2/production/basic_deep/corpus_investigator_agent.py`

Important rule:

- write a Deep agent only if a Basic ReAct agent does not do the job

### Use Graph Only For Explicit Business Journeys

Choose Graph when:

- the service must follow a known business path
- the order of steps matters
- branches are meaningful business decisions
- you need controlled pauses, approvals, clarifications, or safe action points

Business value:

- the workflow is visible and reviewable before execution
- the team can reason about the service as a business journey
- safer for structured operations than a free-form assistant

Repository example:

- `agentic_backend/agents/v2/candidate/bid_mgr/agent.py`

## 2. Decision Table

| If your need is... | Use this | Why |
| --- | --- | --- |
| “Answer well in chat with prompt tuning and maybe a few tools.” | Basic ReAct | Smallest useful v2 shape |
| “Answer in chat, but I need one or more missing business tools.” | ReAct with custom tools | Adds capability without changing the runtime family |
| “Answer in chat, but the assistant must investigate across many tool/model steps.” | Deep agent | Still assistant-shaped, but stronger autonomous investigation |
| “The business requires explicit stages, branches, and guarded transitions.” | Graph agent | Workflow is the product, not only the final answer |

## 3. Basic ReAct Profile

Use a Basic ReAct profile when you want a reusable assistant preset with stronger defaults.

Why this exists:

- many assistants differ mostly by prompt, tags, default tools, and guardrails
- a profile lets you reuse the same small ReAct contract instead of creating a new runtime shape

How to implement it:

1. Start from `BasicReActDefinition`.
2. Create a subclass with your own `agent_id`, `role`, `description`, prompt default, tags, declared tool refs, and guardrails.
3. Keep `policy()` inherited unless you really need a different ReAct policy surface.

Small example:

```python
from pydantic import Field

from agentic_backend.agents.v2.production.basic_react.agent import BasicReActDefinition
from agentic_backend.core.agents.v2.contracts.models import (
    GuardrailDefinition,
    ToolRefRequirement,
)


class MyDomainAssistantDefinition(BasicReActDefinition):
    agent_id: str = "my.domain.react.v2"
    role: str = "Domain assistant"
    description: str = "Answers domain questions using grounded platform tools."
    system_prompt_template: str = Field(default="You are a concise domain assistant.", min_length=1)
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(tool_ref="knowledge.search"),
    )
    guardrails: tuple[GuardrailDefinition, ...] = (
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground answers in available evidence",
            description="Do not present unsupported claims as facts.",
        ),
    )
```

Use this shape when the business question is:

- “Which assistant preset do I need?”

Do not use another runtime just to change:

- prompt text
- default tools
- guardrails
- tags
- field defaults

## 4. ReAct With Custom Tools

Use this when the platform already has the right runtime, but not the right business action.

Why this exists:

- some assistants need a small amount of local business logic
- a tool is often enough
- adding a graph for one missing action is usually overkill

How to implement it:

1. Define tool functions with `@tool(...)`.
2. Use `ToolContext` inside the tool to call shared Fred capabilities when needed.
3. Declare a `ReActAgent` with those tools and a clear system prompt.

Important note:

- local `@tool(...)` functions are still exposed to the runtime as declared Fred tool refs
- they are a developer convenience, not a separate runtime family

Small example:

```python
from agentic_backend.core.agents.v2.authoring import ReActAgent, ToolContext, tool


@tool(
    "my_domain.latest_policy_summary",
    description="Summarize the latest policy note for a given business topic.",
)
async def latest_policy_summary(context: ToolContext, topic: str) -> str:
    hits = await context.search(topic, top_k=3)
    if not hits:
        return f"No policy note found for: {topic}"
    return f"Found {len(hits)} relevant policy note(s) for: {topic}"


class PolicyAssistant(ReActAgent):
    agent_id: str = "my.domain.policy.v2"
    role: str = "Policy assistant"
    description: str = "Answers policy questions with one local business tool."
    tools = (latest_policy_summary,)
    system_prompt_template: str = "Use the local tool when the user asks for policy evidence."
```

Use this shape when the business question is:

- “Which missing action should the assistant be able to perform?”

Do not use this shape to hide a real workflow.

If the service must go through explicit stages such as qualify, verify, ask approval, then publish, you probably need a Graph agent instead.

## 5. Deep Agent Variant

Use a Deep agent only when Basic ReAct is not enough.

Why this exists:

- some assistant tasks need longer autonomous investigation
- but they are still assistant-shaped tasks, not fixed workflows
- the user cares about the final researched answer, not about traversing a visible business graph

How to implement it:

1. Start from `DeepAgentDefinition` or from an internal base such as `BasicDeepAgentDefinition`.
2. Keep the definition small: prompt, declared tool refs, guardrails, and field surface.
3. Reuse the same discipline as ReAct: clear role, explicit tools, business guardrails.

Small example:

```python
from pydantic import Field

from agentic_backend.core.agents.v2 import DeepAgentDefinition, GuardrailDefinition, ReActPolicy, ToolRefRequirement


class CorpusInvestigatorDefinition(DeepAgentDefinition):
    agent_id: str = "my.corpus.investigator.v2"
    role: str = "Corpus investigator"
    description: str = "Investigates a topic across the corpus and returns a grounded synthesis."
    system_prompt_template: str = Field(default="Investigate carefully and synthesize clearly.", min_length=1)
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(tool_ref="knowledge.search"),
    )
    guardrails: tuple[GuardrailDefinition, ...] = (
        GuardrailDefinition(
            guardrail_id="grounding",
            title="Ground claims in corpus evidence",
            description="Say when evidence is missing or inconclusive.",
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            guardrails=self.guardrails,
        )
```

What this means in v2:

- Deep is still in the ReAct execution family
- choose it for stronger assistant behavior, not for explicit workflow modeling

Use this shape when the business question is:

- “Why is a regular assistant not enough for this investigation task?”

If you cannot answer that clearly, stay on Basic ReAct.

## 6. Full Graph Agent

Use a Graph agent when the sequence itself is part of the service contract.

Why this exists:

- some services must follow a known business journey
- you need clear transitions and branch conditions
- the team must be able to inspect the path before running it

How to implement it:

1. Define typed input, state, and output models.
2. Define the business graph with nodes, edges, and conditionals.
3. Implement pure state builders.
4. Implement node handlers for the executable business steps.
5. Build the final typed output from terminal state.

Small skeleton:

```python
from pydantic import BaseModel

from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    GraphAgentDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphNodeDefinition,
)


class MyInput(BaseModel):
    message: str


class MyState(BaseModel):
    message: str
    final_text: str | None = None


class MyOutput(BaseModel):
    content: str


class MyWorkflowDefinition(GraphAgentDefinition):
    agent_id: str = "my.workflow.v2"
    role: str = "Workflow assistant"
    description: str = "Runs a controlled business workflow from intake to response."

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="MyState",
            entry_node="analyze",
            nodes=(
                GraphNodeDefinition(node_id="analyze", title="Analyze request"),
                GraphNodeDefinition(node_id="finalize", title="Finalize"),
            ),
            edges=(
                GraphEdgeDefinition(source="analyze", target="finalize"),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return MyInput

    def state_model(self) -> type[BaseModel]:
        return MyState

    def output_model(self) -> type[BaseModel]:
        return MyOutput

    def build_initial_state(self, input_model: BaseModel, binding: BoundRuntimeContext) -> BaseModel:
        del binding
        model = MyInput.model_validate(input_model)
        return MyState(message=model.message)

    def node_handlers(self) -> dict[str, object]:
        return {"analyze": self.analyze, "finalize": self.finalize}

    async def analyze(self, state: MyState) -> MyState:
        return state.model_copy(update={"final_text": f"Processed: {state.message}"})

    async def finalize(self, state: MyState) -> MyState:
        return state

    def build_output(self, state: BaseModel) -> BaseModel:
        model = MyState.model_validate(state)
        return MyOutput(content=model.final_text or "")
```

Use this shape when the business question is:

- “What path must this service follow every time?”

Do not use a Graph agent only because:

- the task sounds important
- the assistant may call several tools
- you want more structure in the code

Those reasons are not enough on their own.

## 7. Practical Review Checklist

Before merging a new v2 agent, ask:

- Why is this the smallest valid shape for the business need?
- Could this stay a Basic ReAct profile instead?
- If custom tools were added, why are platform tools not enough?
- If Deep was chosen, why does Basic ReAct fail?
- If Graph was chosen, what business journey requires explicit steps and branches?
- Are the prompt, tools, guardrails, and fields all understandable to another developer without runtime archaeology?

## 8. Keep The Authoring Surface Business-Facing

For v2 agent definitions, prefer documenting and reviewing:

- what service the user gets
- why a tool is declared
- why a guardrail exists
- what a field allows a user or admin to tune

Avoid writing author documentation that focuses on:

- generic agent patterns
- framework internals
- abstractions that do not help a developer decide what to build

The main question is always:

**Why does this agent exist for the business, and why is this v2 shape the smallest one that works?**
