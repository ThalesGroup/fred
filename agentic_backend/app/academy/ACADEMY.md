# ACADEMY.md

> A hands-on path to build Fred agents — from **Hello World** to **LLM** to **MCP-enabled**.  
> Every step is production-minded, with tiny, _hover-friendly_ comments that explain **why**, not just **how**.

---

## 0 The mental model

Fred agents are **two-phase objects**:

| Phase           | Method         | What goes here                                                                            | Why it exists                                                                          |
| --------------- | -------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| 1️⃣ Construction | `__init__`     | Cheap, local setup only. No I/O, no awaits.                                               | Keeps object creation instant and safe.                                                |
| 2️⃣ Runtime init | `async_init()` | Heavy setup: build the LangGraph, connect MCP servers, load/warm models, read files, etc. | Fred orchestrates these async in a safe order and wires streaming memory/checkpointer. |

**Rule of thumb**

- **`__init__`** ➜ _instant_ setup (variables, caches, constants). **Never** do network or disk I/O here.
- **`async_init()`** ➜ _real_ setup (anything `await`-able or that could block: MCP, models, files).

Why this matters: a blocking `__init__` would freeze the orchestrator and create fragile start ordering.  
Fred calls **all** agents’ `async_init()` in a controlled, concurrent way, and compiles graphs **after** setup.

---

## 1 What a Fred agent must do

Every agent class must:

1. **Declare tunables** with `AgentTuning` (what the UI can change live).
2. **Build a LangGraph** in `async_init()` (do _not_ compile here).
3. **Return a state _update_** from each node (usually `{"messages": [AIMessage(...)]}`).

Fred then compiles your graph later (wiring streaming memory) and manages execution & streaming.

> Tip: Tuned values are stored in the current `self._tuning`.  
> `get_tuned_text("some.key")` reads the **current** value (UI edits included).

---

## 2) Folder structure for this academy

You can mirror this structure in your repo:

```
academy/
  ACADEMY.md
  00-echo/
    echo.py
  01-llm-responder/
    llm-responder.py
  02-dual-model-responder/
    dual-model-responder.py
```

---

## Steps

### 0) Echo: the MOST minimal viable agent

**What you’ll learn**

- AgentTuning + `async_init()` + one node that returns a **delta** (the new AI message only).

`academy/00-echo/echo.py`:[View Source](https://github.com/YourOrg/YourRepo/blob/main/academy/00-echo/echo.py)

**Key idea:** _Return only the new `AIMessage`_.  
Fred’s stream transcoder already knows the history; the typical logic of an agent is only to add new replies to the conversation.

---

### 1) Responder: LLM call, no tools

**What you’ll learn**

- Inject a system instruction with `with_system(...)`.
- Call your configured model with `await self.model.ainvoke(messages)`.
- Keep the delta pattern.

`academy/01-responder-llm/responder.py` [View Source](https://github.com/YourOrg/YourRepo/blob/main/academy/01-responder-llm/responder.py)

---

## 2) Dual-Model Responder (The Router/Generator Pattern)

**What you’ll learn**

- **Model Specialization**: Use two separate, specialized models to optimize for **speed** and **quality**.
- **State Extension**: Define a custom `TypedDict` state (`DualModelResponderState`) to pass internal results (the `classification`) between nodes.
- **Sequential Graph**: Build a linear LangGraph (`router` $\to$ `generator`) to enforce multi-model workflow order.

`academy/02-dual-model-responder/dual_model_responder.py` [View Source] (using the final, corrected code)

**Key idea:** _A small, fast model (Router) executes first to classify the request and update the shared state. A powerful model (Generator) executes second, using the classification saved in the state to inform its final, high-quality response._
