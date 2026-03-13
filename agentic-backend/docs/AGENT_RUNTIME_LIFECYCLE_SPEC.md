# Agent Runtime Lifecycle Spec

Historical note:

- this document describes the legacy `AgentFlow` split lifecycle
- it remains useful when maintaining v1 agents
- it is no longer the target authoring model for new work

For the current target contract, prefer:

- `docs/AGENT_SPECIFICATION.md`
- `docs/AGENTS.md`
- `docs/RUNTIME_ARCHITECTURE.md`

This document describes the runtime API that now exists in the codebase after the split between structural build and runtime activation.

It is based on the current implementation in:

- `agentic_backend/core/agents/agent_flow.py`
- `agentic_backend/core/agents/agent_factory.py`

It also references the immediate call sites that define the effective semantics:

- `agentic_backend/core/agents/agent_controller.py`
- `agentic_backend/core/agents/structural_graph_builder.py`
- representative concrete agents

The goal is to separate:

1. the intended contract of the API
2. the exact behavior of the current code
3. the mismatches that matter for design review

## 1. Design Goal

The split lifecycle exists to support two different use cases with one agent model:

- normal execution: build a warm agent that is ready to answer messages
- non-activating inspection: inspect graph structure and tuning without activating MCP, models, or other runtime dependencies

In short:

- `build_runtime_structure()` is the structural phase
- `activate_runtime()` is the heavy runtime phase

## 2. Core Terms

These terms are the clearest reading of the code today.

- Constructed agent
  - Python object exists.
  - Settings have been applied.
  - No runtime lifecycle guarantee yet.

- Runtime context set
  - `set_runtime_context(context)` was called.
  - The raw context object is stored on the agent.
  - `_prepared_context` is cleared.
  - This is a light assignment only.

- Runtime context bound
  - `bind_runtime_context(context)` was called.
  - This includes `set_runtime_context(context)`.
  - Context-scoped helpers are created here, currently including `storage_client`.
  - By contract this phase should not perform external I/O.

- Structural runtime
  - The agent has executed `build_runtime_structure()`.
  - `_graph` may now exist for Mermaid rendering.
  - This graph may be a placeholder or conceptual structure, not necessarily the final executable graph.

- Activated runtime
  - The agent has executed `activate_runtime()`.
  - This is where MCP, models, remote clients, file loading, or other heavy setup may occur.

- Compiled runtime
  - `get_compiled_graph()` has returned a `CompiledStateGraph`.
  - In the base class this is cached in `self.compiled_graph`.

- Warm agent
  - The factory has returned an agent that is considered ready for normal execution.
  - On a fresh create this means `initialize_runtime(...)` completed.
  - On cache reuse this means the prior initialized runtime is reused and only the runtime context object is refreshed.

## 3. Base AgentFlow Contract

### `apply_settings(new_settings)`

Current behavior:

- Copies authoritative settings onto the instance.
- Resolves effective tuning into `self._tuning`.
- Keeps `agent_settings.tuning` aligned with that resolved tuning.

Meaning:

- The instance should treat manager-resolved settings as authoritative.
- Runtime lifecycle is separate from settings application.

### `set_runtime_context(context)`

Current behavior:

- Stores `self.runtime_context = context`
- Clears `_prepared_context`

Meaning:

- This is a lightweight context refresh, not a full bind.

### `bind_runtime_context(runtime_context)`

Current behavior:

- Calls `set_runtime_context(runtime_context)`
- Creates `self.storage_client = KfWorkspaceClient(agent=self)`

Intended meaning:

- This is the first real lifecycle step after object creation.
- It should be safe for UI inspection.
- It should not do external I/O.

### `build_runtime_structure()`

Current base behavior:

- No-op

Intended meaning:

- Build deterministic in-memory structures needed to describe the agent runtime.
- This is where `_graph` should normally be created.
- No network or disk I/O should happen here.
- This phase exists specifically so graph inspection can happen without activation.

Important practical reading:

- The codebase no longer guarantees that `_graph` is the final executable graph.
- In some agents `_graph` is a structural graph only.

### `activate_runtime()`

Current base behavior:

- No-op

Intended meaning:

- Perform async or heavy setup.
- Examples: MCP init, model binding, remote clients, loading runtime-only assets.

### `initialize_runtime(runtime_context)`

Current behavior:

- Typed public lifecycle entrypoint.
- Delegates to `async_init(runtime_context=...)`.

Meaning:

- Factory code should call this, not custom lifecycle sequencing per agent.

### `async_init(runtime_context)`

Current default behavior:

- If the subclass does not override `async_init`, the base implementation does:
  - `bind_runtime_context(...)`
  - `build_runtime_structure()`
  - `await activate_runtime()`

Compatibility behavior:

- If a subclass overrides `async_init`, then `super().async_init(...)` becomes bind-only.
- This exists to avoid double initialization in legacy agents.

Observed codebase state:

- There are currently no in-tree overrides of `async_init`.
- So the effective lifecycle in the repository is the new default path.

### `get_graph_mermaid()`

Current behavior:

- If `_graph` is present, compile it with `checkpointer=None`
- Render Mermaid from the compiled graph
- Do not call `get_compiled_graph()`

Meaning:

- Graph rendering is intentionally non-activating.
- This method assumes `_graph` is already available from `build_runtime_structure()`.

### `get_graph_mermaid_preview()`

Current base behavior:

- Returns `None`

Intended meaning:

- Optional manual preview path for agents that cannot expose their runtime graph safely through `_graph`.

Important current fact:

- The main graph controller path does not call this method today.
- It exists in the API, but is not the primary inspection path in production wiring.

### `get_compiled_graph(checkpointer=None)`

Base class behavior:

- If `self.compiled_graph` already exists, reuse it
- Otherwise compile `self._graph` with the provided checkpointer or `self.streaming_memory`
- Cache the compiled graph in `self.compiled_graph`

Meaning:

- Compilation is lazy and idempotent per instance in the base implementation.

Important consequence:

- The first successful compilation fixes the checkpointer for that instance.
- Later calls with another checkpointer still reuse the first compiled graph.

### `astream_updates(...)`

Current behavior:

- Stores the incoming `RunnableConfig` on `self.run_config`
- Calls `get_compiled_graph(checkpointer=self.streaming_memory)`
- Streams from the compiled graph

Meaning:

- Normal execution expects the agent to be fully initialized before streaming starts.
- The stream path assumes runtime activation has already happened if the concrete agent requires it.

## 4. AgentFactory Contract

`AgentFactory.create_and_init(...)` is the public constructor/orchestrator for a warm agent.

### Fresh creation path

Current behavior:

1. Resolve authoritative settings from the manager/service
2. Import the class and instantiate the agent
3. Call `agent.apply_settings(settings)`
4. Call `agent.set_runtime_context(runtime_context)`
5. Call `await agent.initialize_runtime(runtime_context=runtime_context)`
6. Cache the initialized instance under `(session_id, agent_id)`

Interpretation:

- The factory guarantees that a newly created agent has completed its runtime lifecycle before being returned.
- The explicit `set_runtime_context(...)` before `initialize_runtime(...)` is a compatibility guard for older initialization styles.

### Cache reuse path

Current behavior:

1. Lookup cached agent by `(session_id, agent_id)`
2. Increment cache reference count
3. Call `cached.set_runtime_context(runtime_context)`
4. Return the cached instance

Interpretation:

- Cache reuse refreshes the raw runtime context only.
- It does not call `bind_runtime_context(...)`.
- It does not rebuild structure.
- It does not reactivate runtime.
- It assumes runtime resources are session-sticky and remain valid across exchanges.

This is a key semantic point of the current API.

## 5. Non-Activating Graph Inspection Path

The `/agents/{agent_id}/graph` controller currently does:

1. instantiate the agent from settings
2. `bind_runtime_context(RuntimeContext())`
3. `build_runtime_structure()`
4. `get_graph_mermaid()`

It explicitly does not call `activate_runtime()`.

So the effective contract for UI graph rendering is:

- graph inspection must succeed after bind + build only
- activation must not be required for the structural graph path

If the structural path fails, the controller returns a generic fallback Mermaid error graph.

Important current mismatch:

- this controller path does not use `get_graph_mermaid_preview()`
- so agents that rely on a manual preview method are not helped by the current wiring

## 6. Structural Graph vs Executable Graph

The split lifecycle introduced an important semantic change:

- `_graph` no longer clearly means "the one executable graph of the agent"

Today `_graph` can mean one of several things:

- the real executable graph, compiled later by the base class
- a structural placeholder graph used only for Mermaid rendering
- no graph at all until activation

This is the single most important semantic clarification to make explicit in the API.

The clearest reading of the implementation is:

- `_graph` is the agent's structural graph slot
- `get_compiled_graph()` is the executable graph entrypoint
- these may coincide, but they do not always have to

## 7. Effective Agent Categories In The Current Code

### A. Strict split agents

These follow the intended contract cleanly:

- `build_runtime_structure()` builds the graph without I/O
- `activate_runtime()` initializes runtime dependencies
- base `get_compiled_graph()` can compile `_graph`

Representative examples:

- `RagExpert`
- `Archie`
- `AdvancedRagExpert`
- `AegisRagExpert`
- many academy examples

### B. Runtime-dependent graph builders

These defer graph creation until activation:

- `build_runtime_structure()` sets `_graph = None`
- `activate_runtime()` initializes runtime dependencies and then builds `_graph`

Representative examples:

- `Tessa`
- `ContentGeneratorExpert`

Implication:

- They do not currently satisfy the strongest form of "graph is inspectable before activation".

### C. Structural-preview plus runtime-specific compilation agents

These separate preview structure from execution more aggressively:

- `build_runtime_structure()` may build a conceptual or placeholder graph, or nothing
- `activate_runtime()` prepares tools/runtime
- `get_compiled_graph()` constructs the real executable graph on demand

Representative examples:

- `BasicReActAgent`
- `JiraAgent`
- `ReferenceEditor`
- `PptFillerAgent`
- `CoachDG`

Implication:

- For these agents, `_graph` should be understood as structural metadata, not necessarily the executable runtime graph.

### D. Non-LangGraph agents

Representative example:


Implication:

- It lives in the catalog as an `AgentFlow`, but it intentionally does not implement LangGraph execution.
- It sits outside the normal runtime-graph contract.

## 8. Important Ambiguities And Design Tensions

These are the points that should be reviewed if the team wants a sound long-term API.

### 1. Cache refresh is lighter than bind

Today:

- fresh init path eventually performs `bind_runtime_context(...)`
- cache reuse performs only `set_runtime_context(...)`

Risk:

- bind-time helpers such as `storage_client` are not rebuilt on reuse
- "runtime context refreshed" and "runtime context rebound" are not the same thing

### 2. Preview API has two mechanisms

Today there are two different inspection concepts:

- structural `_graph` plus `get_graph_mermaid()`
- manual `get_graph_mermaid_preview()`

But the controller uses only the first one.

Risk:

- the API surface suggests one fallback path, while the production wiring assumes another

### 3. `_graph` is underspecified

Today `_graph` can mean:

- executable graph
- structural-only graph
- absent until activation

Risk:

- developers may think `build_runtime_structure()` must always populate the final runnable graph, but several concrete agents already rely on a weaker interpretation

### 4. Compiled graph caching is single-slot

In the base class:

- `self.compiled_graph` is cached once
- the initial checkpointer wins

Risk:

- a caller can ask for a different checkpointer later and silently get the old compiled graph
- `SimpleAgentFlow` currently compiles during `build_runtime_structure()`, which makes this stick even earlier

### 5. "No compile in build" is intended, but not universal

The academy guidance says not to compile in `build_runtime_structure()`.

Current code exception:

- `SimpleAgentFlow.build_runtime_structure()` calls `self.get_compiled_graph()`

Risk:

- this weakens the phase separation and makes checkpointer semantics less obvious

## 9. Recommended Normative Reading For Review

If the current design is kept, the cleanest specification would be:

- `bind_runtime_context()` means "prepare context-scoped helpers without I/O"
- `build_runtime_structure()` means "produce enough structural information for non-activating inspection"
- `_graph` means "structural graph slot", not necessarily "the exact executable graph"
- `activate_runtime()` means "make the agent executable"
- `get_compiled_graph()` means "return the executable graph, possibly constructed lazily from activated runtime"

That reading matches the direction of the refactor better than the older meaning of `_graph` as always-the-real-graph.

## 10. Review Questions

These are the concrete design questions exposed by the current code:

1. Should cache reuse call `bind_runtime_context(...)` instead of only `set_runtime_context(...)`?
2. Should the graph controller try `get_graph_mermaid_preview()` before or after the structural `_graph` path?
3. Should the contract say that `_graph` is structural, executable, or either?
4. Should `build_runtime_structure()` be required to always support UI graph inspection?
5. Should base compiled-graph caching be keyed by checkpointer, or should compilation remain uncached for some agents?
6. Should `SimpleAgentFlow` stop compiling during `build_runtime_structure()` to preserve the phase separation?

## 11. Bottom Line

The refactor did create a meaningful API split:

- bind
- build structure
- activate runtime
- compile/execute

That part is real and useful.

What is still underspecified is whether the structural graph is:

- the executable graph
- a preview graph
- or simply an optional artifact

The code today already uses all three interpretations, so the API is usable, but not yet fully crisp.

## 12. Essential SDK Extract

The most useful way to understand `AgentFlow` is this:

- `AgentFlow` is the lifecycle shell of an agent, not the business logic itself
- your subclass defines nodes and structure
- `AgentFlow` provides the runtime contract: bind context, compile, stream, and execute
- a typical agent only needs to implement:
  - `build_runtime_structure()`
  - `activate_runtime()`
  - one or more graph nodes

Minimal mental model:

- `__init__`: cheap local state only
- `bind_runtime_context(...)`: Fred binds caller/session context
- `build_runtime_structure()`: build deterministic graph structure, no I/O
- `activate_runtime()`: initialize models, MCP, remote clients
- `get_compiled_graph()`: inherited execution entrypoint
- `astream_updates(...)`: inherited streaming entrypoint

Canonical SDK example:

```python
from __future__ import annotations

import logging

from langchain_core.messages import AnyMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

TUNING = AgentTuning(
    role="example_agent",
    description="Minimal example of a normal Fred agent.",
    tags=["sdk-example"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            required=True,
            default="You are a concise assistant.",
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


@expose_runtime_source("agent.ExampleAgent")
class ExampleAgent(AgentFlow):
    tuning = TUNING

    def build_runtime_structure(self) -> None:
        # Structural phase only.
        # Build the LangGraph topology here, with no network or disk I/O.
        self._graph = self._build_graph()

    async def activate_runtime(self) -> None:
        # Heavy runtime phase.
        # Typical work here: create model clients, init MCP, bind tools.
        self.model = get_default_chat_model()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(MessagesState)
        graph.add_node("answer", self.answer)
        graph.add_edge(START, "answer")
        graph.add_edge("answer", END)
        return graph

    async def answer(self, state: MessagesState) -> MessagesState:
        # AgentFlow does not inject prompts automatically.
        # The node decides what prompt to apply and when.
        system_prompt = self.get_tuned_text("prompts.system") or ""
        messages: list[AnyMessage] = self.with_system(
            system_prompt, state["messages"]
        )

        # ask_model() is the standard normalized model call helper.
        ai_message: AnyMessage = await self.ask_model(self.model, messages)

        # Return only the state delta produced by this node.
        return self.delta(ai_message)
```

How Fred should read this class:

- construction creates a cheap Python object
- the framework binds a `RuntimeContext`
- the framework asks the agent to build its structure
- the framework activates heavy runtime dependencies
- later, execution uses inherited `get_compiled_graph()` and `astream_updates()`

Equivalent lifecycle in pseudo-code:

```python
agent = ExampleAgent(agent_settings=settings)
agent.apply_settings(settings)
await agent.initialize_runtime(runtime_context)

# initialize_runtime() means:
#   agent.bind_runtime_context(runtime_context)
#   agent.build_runtime_structure()
#   await agent.activate_runtime()

compiled = agent.get_compiled_graph()
async for event in agent.astream_updates({"messages": [...]}, config=run_config):
    ...
```

One sentence summary:

`AgentFlow` is the SDK base class that owns lifecycle and execution; the subclass only supplies structure and runtime-specific behavior.
