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

## 2 Folder structure for this academy

You can mirror this structure in your repo:

```
academy/
  ACADEMY.md
  00-echo/
  01-llm-responder/
  02-dual-model-responder/
  03_asset_responder/
  04_slide_maker/
  05_gps_agent/
  06_simple_leader/
  07_travel_agent/
  08_ecoadviser/
```

Each folder contains one or more agent implementations and, when present, a local `README.md` with extra details.

---

## 3 Step‑by‑step modules

### 00 – Echo: the MOST minimal viable agent

Folder: `academy/00-echo`  
Code: `echo.py`  
Docs: `README.md`

**What you’ll learn**

- AgentTuning + `async_init()` + one node that returns a **delta** (the new AI message only).
- Using `MessagesState` and a `StateGraph` with a single node.

Key idea: _Return only the new `AIMessage`_.  
Fred’s stream transcoder already knows the history; the agent only appends new replies.

---

### 01 – LLM Responder: single-model answer, no tools

Folder: `academy/01-llm-responder`  
Code: `llm-responder.py`  
Docs: `README.md`

**What you’ll learn**

- Injecting a tuned system prompt with `with_system(...)`.
- Calling your configured model via `get_default_chat_model()`.
- Using `ask_model(...)` and the `delta(...)` helper to return a clean state update.

This is the first **“real” LLM agent** in the academy.

---

### 02 – Dual‑Model Responder (Router / Generator)

Folder: `academy/02-dual-model-responder`  
Code: `dual-model-responder.py`  
Docs: `README.md`

**What you’ll learn**

- **Model specialization**: a fast router model vs a powerful generator model.
- **State extension**: `DualModelResponderState` carries a `classification` between nodes.
- **Sequential graphs**: `router` → `generator` pattern in LangGraph.

Key idea: _A small, fast model classifies the request; a stronger model uses that classification to craft the final answer._

---

### 03 – Asset Responder: working with files/assets

Folder: `academy/03_asset_responder`  
Code: `asset_responder.py` (see folder)  
Docs: `README.md`

**What you’ll learn**

- How agents can interact with uploaded assets/blobs.
- Where to hook asset logic into the graph (before/after LLM calls).

---

### 04 – Slide Maker: generating content + structure

Folder: `academy/04_slide_maker`  
Code: see `slide_maker.py` in the folder.  
Docs: `README.md`

**What you’ll learn**

- Turning a free‑form request into a structured artifact (slides/sections).
- Returning Markdown that the UI can render nicely.

---

### 05 – GPS Agent: coordinates and simple mapping

Folder: `academy/05_gps_agent`  
Docs: `README.md`

**What you’ll learn**

- Handling latitude/longitude in agent state.
- Emitting geo‑friendly outputs for the UI.

---

### 06 – Simple Leader: multi‑step orchestration

Folder: `academy/06_simple_leader`  
Docs: `README.md`

**What you’ll learn**

- Orchestrating several sub‑steps (or sub‑agents) from a single “leader” agent.
- Basic control‑flow and state passing patterns.

---

### 07 – Travel Agent: OpenStreetMap / Overpass demo

Folder: `academy/07_travel_agent`  
Code: `travel_agent.py`  
Docs: `README.md` (already present)

**What you’ll learn**

- Calling external HTTP APIs (Nominatim, Overpass) from LangGraph nodes.
- Converting natural‑language queries into OSM tag filters.
- Implementing a fallback LLM answer when external services fail.
- Emitting “thought” traces so the UI can show per‑step progress.

Example question: “Nice vegetarian restaurants near Bordeaux?”

---

### 08 – EcoAdvisor: low‑carbon mobility helper

Folder: `academy/08_ecoadviser`  
Code: see `ecoadviser_agent.py` and helpers.  
Docs: `README.md` (already present)

**What you’ll learn**

- Combining open data (e.g. Lyon bike lanes, transit stops) with LLM reasoning.
- Using CSV/Tabular tools to answer impact / mobility questions.
- Producing user‑friendly reports with CO₂ estimates and alternatives.
