# 01 – LLM Responder

This step turns the minimal Echo agent into a **real LLM‑backed responder**.

## What it shows

- How to get a default chat model via `get_default_chat_model()`.
- How to inject a tuned system prompt with `with_system(...)`.
- How to call the model and normalize the result with `ask_model(...)`.
- How to return the new AI message as a **delta** using `self.delta(ai)`.

## Files

- `llm-responder.py` – implementation of `agent.Responder`.

Use this as a template when you need a simple “answer my question” agent with no tools or external APIs.
