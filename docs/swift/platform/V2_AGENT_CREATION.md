# Fred Agents: Shapes, Shipping, and Tunings

This document explains the current Fred v2 model for agents:

- what an agent is
- how a pod exposes agents to the platform
- how the control plane turns templates into team-managed instances
- how tunings are exposed to admins and the UI without creating configuration hell

Use this as the high-level guide before reading the lower-level contracts in:

- [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md)
- [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)

---

## 1. The Mental Model

In Fred, the runtime pod is the **author** of an agent template.

The control plane is **not** an agent authoring system. It:

- discovers templates from runtime pods
- lets a team create a managed agent instance from one template
- stores the instance's chosen tuning values
- resolves that instance back to the pod at execution time

The frontend is an **administration and chat surface**, not a graph/prompt editor.

---

## 2. Agent Shapes

Fred currently has three agent shapes:

| Shape                  | When to use it                                                 | Tuning model                                                             |
| ---------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `ReActAgentDefinition` | Conversational assistants with tools and a broad system prompt | Best for a global prompt plus a small number of business settings        |
| `GraphAgentDefinition` | Explicit workflows, step routing, HITL, business state         | Best when the agent needs step-specific prompts and typed workflow state |
| `DeepAgentDefinition`  | Deep research / longer multi-step assistant behavior           | Same tuning model as ReAct; it is a specialized ReAct-family runtime     |

Important simplification:

- `DeepAgentDefinition` is not a separate tuning family
- for tuning and UI purposes, think in two buckets:
  - ReAct/Deep
  - Graph

---

## 3. How An Agent Reaches A User

The end-to-end path is:

1. A development team writes and ships agent definitions inside a Fred runtime pod.
2. The pod exposes those definitions through `GET /agents/templates`.
3. Control-plane aggregates those templates into `AgentTemplateSummary`.
4. A team admin creates a managed agent instance from one template.
5. Control-plane stores the instance's chosen tuning values.
6. At execution time, control-plane resolves the instance back to the pod and forwards its stored tuning payload.

That means one user-visible managed agent is always:

- based on one runtime-authored template
- configured by one team-scoped stored tuning payload
- executed by the original runtime pod implementation

---

## 4. The Tuning Taxonomy

To stay in control, Fred should treat tunings as four different animals.

### 4.1 `prompts.*`

Prompt fields are **author instructions**.

Use them when an admin needs to influence what the agent says or how one reasoning
phase is instructed.

Examples:

- `prompts.system`
- `prompts.planning`
- `prompts.routing`
- `prompts.self_check`

Rules:

- `prompts.system` is the broad per-instance assistant prompt override
- `prompts.<step_or_operation>` is for narrower prompt injection into one step or phase
- prompt keys should be few, stable, and meaningful to the business workflow

### 4.2 `settings.*`

Settings fields are **runtime or business behavior knobs**.

Use them for typed values that change execution behavior without rewriting prompts.

Examples:

- `settings.delay_ms`
- `settings.verbose`
- `settings.threshold`
- `settings.max_candidates`

Rules:

- settings should be typed and bounded
- settings should describe behavior, not UI
- if a setting is really platform infrastructure, it should not be a generic setting field

### 4.3 `chat_options.*`

Chat-option fields are **frontend hints**.

Use them when a managed agent instance needs the chat UI to expose or hide a UX capability.

Examples:

- `chat_options.attach_files`
- `chat_options.libraries_selection`

Rules:

- these are primarily consumed by the frontend
- they should not carry core business behavior
- they should stay small and UI-oriented

### 4.4 Platform Selectors Are Not Generic Tuning Fields

Some configuration must stay **platform-owned**, not agent-field-owned.

The two important examples are:

- MCP server selection
- model profile selection / model routing policy

These should use dedicated managed-agent contract fields such as:

- `selected_mcp_server_ids`
- `model_profile_id`

They should **not** be reintroduced as ad hoc generic keys like:

- `settings.model`
- `prompts.model_name`
- `tools.enabled`

Reason:

- provider/model/tool selection is governance and deployment policy
- prompt and settings fields are agent behavior authoring
- mixing both creates configuration hell quickly

---

## 5. The Special Rule For `prompts.system`

`prompts.system` is mandatory as a concept, but optional as an override value.

Meaning:

- every ReAct/Deep agent already has an author-defined `system_prompt_template`
- every complex Graph agent should also define one broad system-level instruction concept
- a managed instance may override that broad prompt through `prompts.system`

Execution rule:

- for ReAct/Deep, runtime additionally mirrors non-blank `prompts.system` onto `system_prompt_template`
- for Graph, node handlers read `context.tuning_values["prompts.system"]` directly when they need it

Operational rule:

- blank `prompts.system` means "keep the author default"
- step prompts such as `prompts.planning` do not replace the global system prompt; they refine one phase

---

## 6. ReAct, Graph, and Deep Authoring Guidance

### 6.1 ReAct / Deep

Prefer:

- one global `prompts.system`
- a very small number of `settings.*` fields
- optional `chat_options.*` hints

Avoid:

- large numbers of per-phase prompt fields unless the runtime actually has named phases worth exposing
- raw model/provider fields

### 6.2 Graph

Graph agents are the right place for:

- `prompts.system` as the broad workflow instruction layer
- `prompts.<step_or_operation>` for step-specific guidance
- typed `settings.*` values for thresholds, verbosity, delay, limits, and feature flags

Graph agents should prefer typed state for business facts and use prompt fields only for actual instructions.

### 6.3 Deep

Deep agents should be documented and administered like ReAct-family assistants unless and until they gain a truly distinct managed tuning contract.

---

## 7. Guardrails Against Configuration Hell

When adding a new tuning, ask:

1. Is this really an agent-authored prompt?
2. Is this really a typed behavior setting?
3. Is this really a frontend-only chat option?
4. Or is this actually a platform selector that deserves its own typed contract?

Preferred order:

1. Reuse an existing tuning key.
2. Add a typed `settings.*` field if the value is truly agent behavior.
3. Add a `prompts.<phase>` field only when a real reusable phase exists.
4. Add a dedicated platform contract field for MCP/model/governance concerns.

Avoid:

- exposing every internal step as a user-facing tuning
- storing provider names or raw model names in generic tuning fields
- using prompt fields for booleans, thresholds, or selectors
- using chat options for runtime behavior

---

## 8. Recommended Default Policy

For a stable first `swift` release, the safest architecture is:

- use `prompts.system` as the one broad prompt override every managed agent understands
- allow Graph agents to add a small number of named step prompts when they have durable business value
- keep `settings.*` typed and sparse
- keep `chat_options.*` strictly frontend-oriented
- keep model routing policy-based and operation-aware, not prompt-driven
- keep MCP and model selection in dedicated managed-agent contract fields

This keeps the agent surface declarative while preserving central governance.
