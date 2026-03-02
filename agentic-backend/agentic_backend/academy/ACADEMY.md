# ACADEMY.md

> A hands-on set of remaining capability demos for Fred.  
> Every step is production-minded, with tiny, _hover-friendly_ comments that explain **why**, not just **how**.

---

## 0 The mental model

Fred agents are **construction + split-runtime lifecycle** objects:

| Phase               | Method                      | What goes here                                                                   | Why it exists                                           |
| ------------------- | --------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 1️⃣ Construction     | `__init__`                  | Cheap, local setup only. No I/O, no awaits.                                      | Keeps object creation instant and safe.                 |
| 2️⃣ Bind context     | `bind_runtime_context(...)` | Attach caller/session identity and helpers. No I/O.                              | Lets Fred pass user identity before runtime activation. |
| 3️⃣ Build structure  | `build_runtime_structure()` | Build LangGraph topology / prompts / deterministic in-memory structures. No I/O. | Enables safe graph inspection and predictable setup.    |
| 4️⃣ Activate runtime | `activate_runtime()`        | Heavy setup: connect MCP servers, load/warm models, read files, remote clients.  | Fred orchestrates async setup after context is known.   |

**Rule of thumb**

- **`__init__`** ➜ _instant_ setup (variables, caches, constants). **Never** do network or disk I/O here.
- **`build_runtime_structure()`** ➜ deterministic graph/prompt setup. **No** network or disk I/O here.
- **`activate_runtime()`** ➜ _real_ setup (anything `await`-able or that could block: MCP, models, files).

Why this matters: a blocking `__init__` would freeze the orchestrator and create fragile start ordering.  
Fred now calls `initialize_runtime(...)` (which orchestrates bind → build → activate), and can render a **structural graph** without activating MCP/tooling.

---

## 1 What a Fred agent must do

Every agent class must:

1. **Declare tunables** with `AgentTuning` (what the UI can change live).
2. **Build a LangGraph** in `build_runtime_structure()` (do _not_ compile here).
3. **Activate runtime dependencies** (models/MCP/clients) in `activate_runtime()`.
4. **Return a state _update_** from each node (usually `{"messages": [AIMessage(...)]}`).

Fred then compiles your graph later (wiring streaming memory) and manages execution & streaming.

> Tip: Tuned values are stored in the current `self._tuning`.  
> `get_tuned_text("some.key")` reads the **current** value (UI edits included).

---

## 2 Folder structure for this academy

You can mirror this structure in your repo:

```
academy/
  ACADEMY.md
  04_slide_maker/
```

Each folder contains one or more agent implementations and, when present, a local `README.md` with extra details.

---

## 3 Remaining modules

Early `AgentFlow` tutorial agents and exploratory workflow demos have been retired. The remaining academy modules focus on a few still-useful UI/runtime capability patterns.

### 04 – Slide Maker: generating content + structure

Folder: `academy/04_slide_maker`  
Code: see `slide_maker.py` in the folder.  
Docs: `README.md`

**What you’ll learn**

- Turning a free‑form request into a structured artifact (slides/sections).
- Returning Markdown that the UI can render nicely.

---

### 09 – Downloadable report pattern in v2

**What you’ll learn**

- Using a v2 ReAct agent to draft a useful report or summary.
- Publishing that generated file through Fred storage.
- Returning a structured `LinkPart` download response for the UI without
  relying on legacy `AgentFlow` helpers.
