# 02 – Dual‑Model Responder (Router / Generator)

This step introduces a **multi‑model pattern**: a fast router model plus a powerful generator model.

## What it shows

- How to configure **two different models** via `AgentTuning`.
- How to build a custom graph state (`DualModelResponderState`) that carries a `classification`.
- How to route requests through:
  1. `router_node` – small, deterministic model decides `SIMPLE` vs `COMPLEX`.
  2. `generator_node` – larger model generates the final answer using that classification.

## Files

- `dual-model-responder.py` – implementation of `agent.DualModelResponder`.

Use this pattern when you want cheap pre‑classification or routing before expensive generation.
