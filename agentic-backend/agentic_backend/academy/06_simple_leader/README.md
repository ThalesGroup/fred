# 06 – Simple Leader

This step illustrates a **“leader” agent** that orchestrates multiple sub‑steps (or sub‑agents).

## What it shows

- Designing a LangGraph where one agent coordinates several actions.
- Passing intermediate decisions/results through the shared graph state.
- Implementing simple control‑flow (e.g. retry / branch / stop) at the leader level.

## Files

- `mini_llm_orchestrator.py` and related files – see this folder for the orchestration logic.

Use this as a template when you want a single entrypoint agent that delegates work to other agents or tools.
