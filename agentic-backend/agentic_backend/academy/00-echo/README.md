# 00 – Echo Agent

This is the **minimal Fred agent** used to introduce the core concepts.

## What it shows

- How to declare `AgentTuning` so the UI can edit a system prompt.
- How to implement `async_init()` and build a tiny `StateGraph`.
- How to write a single node that returns a **state delta**:
  - `{"messages": [AIMessage(...)]}` only, no full state rewrite.

## Files

- `echo.py` – the agent implementation (`agent.Echo`).

Use this step as a starting template when creating a brand‑new agent. It has **no LLM call**, just the plumbing, so you can focus on structure first.
