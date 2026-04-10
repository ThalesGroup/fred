# RAG Agents In Fred

This page is kept as a focused note on RAG agents.
It is no longer meant to prescribe `AgentFlow` as the default implementation model.

## 1. Current Recommended Direction

For new RAG work in Fred, prefer v2 ReAct authoring:

- agent definition stays pure
- retrieval is expressed through tools
- Fred runtime owns execution, streaming, and output shaping

Current concrete v2 example:

- `agentic_backend/agents/v2/production/basic_react/profiles/rag_expert.py`

## 2. What A Good Fred RAG Agent Should Expose

A RAG agent in Fred usually needs:

- a prompt that clearly distinguishes grounded facts from uncertain answers
- one or more retrieval tools
- structured citations / sources
- optional scoped retrieval options from chat context

In v2, that typically means:

- `ReActAgentDefinition`
- a retrieval tool such as `knowledge.search`
- final answers that carry sources in metadata

Important authoring rule:

- declare retrieval through a Fred business tool ref such as `knowledge.search`
- do not make a new v2 RAG agent depend directly on a raw MCP endpoint such as
  `mcp-knowledge-flow-mcp-text` when the platform already exposes the retrieval
  capability in a transport-agnostic way

The point is not to hide MCP exists.
The point is to keep the product-agent contract stable while Fred remains free
to route that capability through the most appropriate backend integration.

## 3. Legacy RAG Agents

Legacy agents such as `Rico`, `AdvancedRico`, `Aegis`, and `Archie` still exist.
They are important for migration and behavior comparison, but they are not the target authoring model.

## 4. Why v2 Is Better For New RAG Work

The v2 shape makes RAG easier to reason about:

- tool contract is explicit
- inspection is safe
- runtime policy is platform-owned
- structured outputs survive through the chat stack

This is the main reason `RAG Expert V2` exists: it proves that RAG behavior can be expressed cleanly without pushing lifecycle or graph compilation into the author class.
