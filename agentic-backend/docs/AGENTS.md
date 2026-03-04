# Fred Agent Authoring Guide (v2-first)

This document describes the authoring model Fred now wants to standardize.

Short version:

- new agents SHOULD be written in the v2 model
- `AgentFlow` is now legacy maintenance surface
- Fred owns runtime lifecycle, execution, inspection, checkpointing, and MCP wiring
- v2 still uses a warm per-`(session, agent)` in-memory cache
- durable checkpoints complement that cache; they do not replace it

The goal is not to expose LangGraph directly to every agent author.
The goal is to expose a stable Fred SDK above the runtime engine.

Useful reading order:

- current doc status map: [DOC_STATUS.md](/home/dimi/run/reference/fred/agentic-backend/docs/DOC_STATUS.md)
- current feature surface: [FEATURE_MAP.md](/home/dimi/run/reference/fred/agentic-backend/docs/FEATURE_MAP.md)
- graph runtime maturity and remaining LangGraph usage: [GRAPH_RUNTIME_MATURITY_AND_LANGGRAPH_USAGE.md](/home/dimi/run/reference/fred/agentic-backend/docs/GRAPH_RUNTIME_MATURITY_AND_LANGGRAPH_USAGE.md)
- explicit v2 trade-offs against middleware/framework-native layering: [RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](/home/dimi/run/reference/fred/agentic-backend/docs/RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md)

## 1. Preferred Authoring Model

Fred now has two authoring worlds:

- legacy: `AgentFlow`
- current target: `AgentDefinition`

For new work, prefer:

- `ReActAgentDefinition` for most conversational or tool-using agents
- `GraphAgentDefinition` for richer deterministic workflows with explicit state and branching

Concrete examples already present in the repo:

- `agentic_backend/agents/v2/production/basic_react/agent.py`
- `agentic_backend/agents/v2/production/basic_react/profiles/rag_expert.py`
- `agentic_backend/agents/v2/demos/postal_tracking/agent.py`
- `agentic_backend/agents/v2/samples/tutorial_tools/agent.py`

Folder intent in `agents/v2/`:

- `samples/`: copy/paste-ready authoring starters (not catalog-wired by default)
- `demos/`: executable demonstrations for runtime capabilities
- `candidate/`: exploratory agents under active evaluation
- `production/`: agents intended for real usage

## 2. What The Author Owns

In v2, the author owns the pure declaration of the agent:

- metadata: `agent_id`, `role`, `description`, `tags`
- editable fields
- declared tool requirements
- execution description:
  - ReAct policy
  - or graph topology + node handlers

The author does not own:

- runtime activation
- MCP session lifecycle
- compiled graph caching
- checkpoint strategy
- session streaming protocol
- inspection endpoint behavior

That belongs to Fred runtime.

## 3. ReAct Agents

Use `ReActAgentDefinition` when the agent is fundamentally:

- a prompt/policy
- a set of tools
- optional guardrails
- optional approval policy

This is the default path for:

- general assistants
- RAG assistants
- operational assistants
- most tool supervisors

Examples:

- `Basic ReAct V2`
- `RAG Expert V2`
- profile-based agents such as `custodian`, `sentinel`, `georges`, `log_genius`, `geo_demo`

Profiles are only a convenient initialization layer.
They are not a separate runtime model.

Observability note for ReAct in v2:

- ReAct runtime instrumentation is shared and enforced centrally, not left to each agent author.
- The runtime emits a standard model-call span (`v2.react.model`, `operation=model_call`) and shared metadata context for Langfuse filtering.
- Compared to legacy v1-style agent-local runtime wiring, this reduces per-agent drift in tracing quality.

## 4. Graph Agents

Use `GraphAgentDefinition` when the agent needs:

- typed workflow state
- explicit deterministic branching
- multiple business steps
- richer HITL checkpoints
- structured outputs such as `GeoPart` or `LinkPart`

The important boundary is:

- author describes graph structure and node behavior
- Fred runtime executes it

Authors should not directly manage LangGraph runtime objects in new code.
LangGraph remains an implementation engine, not the author-facing SDK.

## 5. Inspection, Not “Graph”

The canonical safe introspection surface is now `inspect`.

What inspection gives:

- metadata
- fields
- execution category
- tool requirements
- a safe preview artifact

What inspection must not do:

- activate MCP
- build remote clients
- compile executable runtime state

## 6. Runtime Cache And Durable Checkpoints

One important point is easy to miss:

- v2 still has an in-memory warm agent cache
- v2 also has durable checkpointing

These are not duplicates.

The warm cache is there so a hot conversation can keep reusing the same
session-scoped runtime instance without rebuilding everything on every turn.

The durable checkpointer is there so runtime continuity can survive things the
warm cache cannot survive, such as:

- backend restart
- runtime rebuild
- HITL pause/resume
- future non-WebSocket execution adapters

So the current v2 model is:

- cache = performance and hot-session continuity
- checkpointing = durable runtime continuity

This is especially relevant for ReAct agents, where durable checkpointing may
add some latency on the happy path even though a warm cached runtime already
exists.

For ReAct agents, preview is usually text.
For true graph agents, preview may be Mermaid.

## 6. MCP and Tools

For v2 authors, MCP should appear as a platform capability, not as hand-managed client lifecycle.

Current shapes:

- declared tool refs through `tool_requirements`
- runtime-provided MCP tools through Fred runtime/tool provider
- built-in v2 tools such as:
  - `knowledge.search`
  - `logs.query`
  - `geo.render_points`
  - `traces.summarize_conversation`

The important rule is:

- declare what the agent needs
- let Fred bind how the tools are actually provided

More precisely:

- agent definitions should declare a stable business capability such as
  `knowledge.search`
- agent definitions should not hard-code a specific MCP endpoint or server id
  when Fred already exposes that capability through a first-class tool ref
- MCP server ids and endpoint wiring are platform/infrastructure concerns, not
  the primary authoring contract for product agents

Example:

- prefer `ToolRefRequirement(tool_ref="knowledge.search")`
- do not make the agent definition depend directly on
  `mcp-knowledge-flow-mcp-text` just to perform standard corpus retrieval

Rule of thumb:

- if Fred already exposes a business tool ref, use it
- if a needed capability exists only behind raw MCP and this starts recurring
  across agents, treat that as pressure to elevate a new Fred capability rather
  than copying transport details into each agent

Note:

- a first-class Fred tool ref is not automatically MCP-backed
- `traces.summarize_conversation` is implemented through Langfuse Public API
  calls, not through MCP

For a practical retest checklist of the current v2 world, see
[FEATURE_MAP.md](./FEATURE_MAP.md).

## 7. HITL and Structured UI Capabilities

Two v2 capability families are important:

- execution control:
  - tool approval
  - richer workflow HITL in graph runtimes
- managed resources:
  - fetch an admin-provided template or style guide through the v2 resource reader
  - publish a generated file through the v2 artifact publisher
- structured outputs:
  - `LinkPart`
  - `GeoPart`
  - sources/citations

These are platform capabilities.
They should not be rebuilt ad hoc inside every agent.

Important clarification:

- in Fred v2, HITL is not limited to "choose one option among N"
- HITL also covers pauses where the runtime expects a free-text human reply,
  for example a clarification request in a workflow
- the common platform contract is: the runtime pauses, emits `awaiting_human`,
  persists a checkpoint, then resumes with an explicit human payload

## 8. Migration Guidance

When looking at an existing legacy agent, the usual decision tree is:

1. Is it mainly prompt + tools + optional approval?
   Then it is probably a `ReActAgentDefinition`.

2. Is it a real multi-step business workflow with typed state?
   Then it is probably a `GraphAgentDefinition`.

3. Is it only a tutorial or prototype?
   Then it probably should not survive as a product agent.

## 9. Legacy Agents

`AgentFlow` is still present because Fred still has legacy agents in production.
That does not make it the target authoring model.

Use `AgentFlow` only when:

- maintaining a legacy agent that has not been ported yet
- debugging historical behavior during migration

Do not choose `AgentFlow` for new product work unless there is a very explicit platform reason.

Legacy v1-oriented guides are grouped in:

- `docs/deprecated/v1/`

## 10. Related Docs

- `docs/AGENT_SPECIFICATION.md`
- `docs/GRAPH_RUNTIME_CONTRACT.md`
- `docs/GRAPH_RUNTIME_CONTRACT.md` (see especially the section on
  conversation history vs runtime checkpoints)
- `docs/RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md`
- `docs/RUNTIME_ARCHITECTURE.md`
- `docs/GENAI_SDK_SPEC.md`
- `docs/GENAI_SDK_COMPATIBILITY_CHALLENGE.md`
