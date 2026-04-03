# Chat Runtime Architecture (v2-first)

This document describes the runtime architecture as it exists now, with both:

- legacy `AgentFlow` support
- v2 runtimes (`ReActRuntime`, `GraphRuntime`)

The target direction is clear:

- authors declare `AgentDefinition`
- Fred owns runtime lifecycle and execution
- chat/session infrastructure stays transport-oriented

## 1. High-Level Flow

1. WebSocket receives a typed chat event (`ask` or `human_resume`)
2. `SessionOrchestrator` ensures the session exists
3. `AgentFactory` returns a warm agent instance:
   - legacy `AgentFlow`
   - or `V2SessionAgent` wrapping a v2 runtime
4. Minimal history is restored when needed
5. User message is emitted immediately
6. `StreamTranscoder` runs the agent and converts runtime events into `ChatMessage`
7. Final exchange messages are persisted and returned

The controller is intentionally thin.
Runtime semantics live below it.

## 2. Main Components

- WebSocket controller
  - `agentic_backend/core/chatbot/chatbot_controller.py`
- Session orchestration
  - `agentic_backend/core/chatbot/session_orchestrator.py`
- Agent loading and warm instance caching
  - `agentic_backend/core/agents/agent_factory.py`
- v2 runtime contracts
  - `agentic_backend/core/agents/v2/contracts/models.py`
  - `agentic_backend/core/agents/v2/contracts/runtime.py`
- v2 executable runtimes
  - `agentic_backend/core/agents/v2/react/react_runtime.py`
  - `agentic_backend/core/agents/v2/graph_runtime.py`
- v2 legacy bridge
  - `agentic_backend/core/agents/v2/legacy_bridge/agent_settings_bridge.py`
  - `agentic_backend/core/agents/v2/legacy_bridge/runtime_context_bridge.py`
  - `agentic_backend/core/agents/v2/legacy_bridge/runtime_bootstrap.py`
- v2 compatibility bridge to the current chat stack
  - `agentic_backend/core/agents/v2/session_agent.py`
- chat event transcoding
  - `agentic_backend/core/chatbot/stream_transcoder.py`
- MCP runtime / tool provider layer
  - `agentic_backend/common/mcp_runtime.py`
  - `agentic_backend/integrations/v2_runtime/adapters.py`

## 3. Streaming Protocol

`StreamTranscoder` emits partial assistant frames using a **delta protocol**: each frame carries only the new text fragment since the previous frame (`metadata.extras.streaming_delta = true`). The frontend accumulates deltas; the final authoritative frame (no flag) replaces the buffer as a consistency checkpoint.

The flush interval controls how often buffered tokens are sent. It is tunable via `ai.stream_flush_interval_ms` in `configuration.yaml` (default: 100 ms). Raise to 200 ms on high-concurrency deployments to reduce WebSocket write frequency at no perceptible cost to streaming smoothness.

See `docs/PROTOCOL.md` for the full wire format.

## 4. Authoring vs Runtime Boundary

This is the most important split.

### Author-facing layer

The author provides:

- `AgentDefinition`
- `ReActPolicy` or `GraphDefinition` plus node handlers
- tuning fields

For tool-aware families such as ReAct and Graph, the author also provides:

- declared Fred tool refs
- optional default MCP servers

### Platform-owned layer

Fred runtime owns:

- context binding
- activated clients and models
- checkpointing
- executor creation
- streaming and persistence
- inspection

This is what moves Fred closer to a platform model instead of a collection of custom LangGraph classes.

Legacy-bridge note:

- `v2/legacy_bridge/` is the explicit home for code that still depends on
  legacy `AgentSettings`, legacy `RuntimeContext`, or the mixed `AgentFactory`
  world
- when reviewing pure v2 runtime behavior, start with `contracts/`, `react/`,
  `support/`, `deep_runtime.py`, and `graph_runtime.py`
- when removing migration code later, `legacy_bridge/` is the first folder to
  shrink or delete

Context-binding note:

- `BoundRuntimeContext.portable_context` is the preferred v2-facing context contract
- `BoundRuntimeContext.runtime_context` still exists as a transitional compatibility
  bridge for legacy Fred runtime concerns not yet lifted into explicit v2 ports or
  portable fields
- new runtime code should prefer portable context and explicit ports over growing
  direct dependency on legacy runtime context

## 5. Two Executable v2 Categories Today

### 5.1 ReActRuntime

Used for:

- `Basic ReAct V2`
- `RAG Expert V2`
- profile-driven agents such as `custodian`, `sentinel`, `georges`, `log_genius`, `geo_demo`

Runtime responsibilities:

- resolve chat model
- merge declared Fred tool refs and runtime MCP tools into one runtime tool surface
- manage tool approval
- stream tool activity and final answer
- propagate structured outputs such as sources, `GeoPart`, `LinkPart`

### 5.2 GraphRuntime

Used for:

- `PostalTrackingDefinition`

Runtime responsibilities:

- build typed initial state
- execute deterministic node handlers
- route on explicit graph conditionals
- call declared and runtime tools
- pause/resume on HITL
- emit structured final output with UI parts

This runtime is the main proof that `GraphAgentDefinition` is not only an inspection toy.

## 6. Session Bridge

The current chat pipeline still expects a legacy `astream_updates(...)` surface.

`V2SessionAgent` is the explicit bridge:

- it adapts ReAct input from restored `HumanMessage` / `AIMessage` / `ToolMessage`
- it adapts graph input from chat state to the graph input model
- it converts v2 runtime events into the minimal legacy event shapes already understood by `StreamTranscoder`

This keeps migration risk contained.

Important consequence:

- the chat stack does not need to know whether the v2 runtime underneath is ReAct or Graph

## 7. Inspection

Inspection is now separate from execution.

Canonical endpoint:

- `/agentic/v1/agents/{agent_id}/inspect`

Inspection is:

- metadata-first
- non-activating
- safe for UI

Preview shape depends on agent category:

- ReAct: text preview
- Graph: Mermaid preview

The old “graph endpoint” is no longer the conceptual model.

## 8. MCP and Runtime Tools

Fred currently uses two complementary tool paths:

- declared tool refs, invoked through `ToolInvokerPort`
- runtime-provided tools, typically via MCP, provided by `ToolProviderPort`

Current adapters:

- `FredKnowledgeSearchToolInvoker`
- `FredMcpToolProvider`

This is already close to the kind of capability split a `genai_sdk`-style substrate would want.

## 9. Structured UI Capabilities

The runtime can now transport structured output parts directly:

- `LinkPart`
- `GeoPart`
- sources/citations

These are no longer tied to bespoke legacy agents.
They are runtime capabilities that both ReAct and Graph can emit.

## 10. HITL

Two HITL modes now exist in practice:

- ReAct tool approval
- richer graph workflow pauses

Transport-wise, both end up as explicit pause/resume semantics in chat.

The runtime target remains:

- author requests human interaction through Fred contracts
- Fred owns pause, checkpoint, resume, and UI payload shape

## 11. Current Limitations

The v2 architecture is real, but not finished.

Still open:

- richer graph-node authoring contract beyond the current first slice
- broader internal capability model
- UI work for inspection rendering
- eventual reduction of legacy `AgentFlow` usage
- a cleaner future bridge toward `genai_sdk` contracts below the runtime layer

## 12. Architectural Direction

The intended direction is now:

- `AgentDefinition` as the authoring SDK
- Fred runtime as the execution platform
- LangGraph as an implementation engine
- optional future `genai_sdk` compatibility as a capability substrate below the runtime

That is the frame in which new work should be evaluated.
