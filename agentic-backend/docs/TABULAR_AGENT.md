# Tabular Agents In Fred

This page summarizes the position of tabular/data agents in the current architecture.

## 1. Present Situation

`Tessa` is still a legacy `AgentFlow` agent and remains useful as a production reference.
It demonstrates:

- MCP-backed tool usage
- reasoning over tabular data
- explicit tool binding

## 2. Architectural Reading Today

From the v2 point of view, `Tessa` is not important because it is “LangGraph-based”.
It is important because it represents a class of agent with:

- strong external tool dependence
- deterministic domain rules
- potentially rich structured output

That means it is a future migration candidate, but not yet a completed v2 port.

## 3. Likely v2 Shape

There are two plausible future shapes:

- `ReActAgentDefinition`
  - if the core behavior remains prompt + tool reasoning
- `GraphAgentDefinition`
  - if the workflow becomes more explicitly staged and deterministic

The choice should be made on behavior, not on historical implementation.

## 4. What Matters For A Future Port

The important pieces to preserve are:

- explicit dataset discovery/query tools
- safe MCP lifecycle
- robust answer formatting
- clear distinction between tool results and final user-facing answer

## 5. Recommendation

Do not use this page as a template for new agents.
Use it as:

- a migration reference
- a reminder of the tabular use case
- a candidate for future v2 design work
