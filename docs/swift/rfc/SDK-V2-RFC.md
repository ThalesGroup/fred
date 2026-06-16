# RFC: Fred SDK V2 for Industrial-Grade Agent Authoring

- Status: Draft
- Authors: Dimitri Tombroff
- Intended audience: Fred maintainers, SDK contributors, agent authors, platform architects
- Scope: Agent authoring model, runtime constraints, author-facing abstractions
- Non-goals: LLM benchmark strategy, model provider comparison, prompt optimization framework

---

## 1. Summary

Fred SDK V2 aims to provide an **authoring framework for reliable, production-grade agents**.

The main goal is not to maximize agent freedom. The main goal is to make it possible for agent authors to create useful agents **without accidentally introducing fragile, untestable, or unsafe behavior**.

This RFC proposes a design direction where:

- the SDK owns execution concerns and operational guarantees,
- agent authors work with constrained, high-level primitives,
- deterministic code handles orchestration and failure behavior,
- language models are used as bounded capabilities rather than as the main control plane.

The target outcome is to reduce the risk of "industrial catastrophes" caused by agents whose real behavior depends on fragile hidden instructions, ad hoc orchestration, or inconsistent runtime patterns.

---

## 2. Problem Statement

### 2.1 Current industry failure mode

Many current agent stacks make it easy to build demos and hard to build reliable systems.

Common failure modes include:

- business logic embedded in prompts,
- inconsistent tool error handling,
- hidden retries or fallback behavior,
- non-deterministic routing,
- poor observability of why an agent behaved a certain way,
- weak testability,
- excessive per-agent custom orchestration.

The result is an ecosystem where agents are often easy to create but difficult to:

- review,
- test,
- maintain,
- evolve,
- certify,
- operate safely.

### 2.2 Why this is especially dangerous

The main risk is not only model hallucination. The larger risk is **architectural opacity**.

An industrial agent can fail because:

- a tool exception is handled differently in each agent,
- a state transition is implicit instead of explicit,
- a model prompt accidentally carries orchestration semantics,
- an author copies a sample without understanding the operational consequences.

This creates systems that appear to work until they are scaled, audited, or placed in a constrained production environment.

---

## 3. Design Goal

Fred SDK V2 should help authors produce agents that are:

- understandable,
- constrained,
- observable,
- testable,
- evolvable,
- safe by default.

The SDK should reduce accidental complexity by centralizing the parts that should not vary from one agent to another.

---

## 4. Primary Design Principle

> The SDK should absorb operational and orchestration complexity so that agent authors can focus on business intent without having to re-implement reliability patterns.

This means the SDK should own, as much as possible:

- execution lifecycle,
- async behavior,
- observability,
- tool invocation discipline,
- error semantics,
- state transition rules,
- structured model invocation,
- artifact publishing conventions,
- human choice patterns,
- authoring constraints.

This is not an anti-LLM position. It is an anti-fragility position.

---

## 5. Audience Clarification: Authors More Than Developers

Fred must be designed for **agent authors**, not only framework developers.

An agent author may be:

- a domain engineer,
- a platform engineer,
- a technical product owner,
- a knowledgeable developer who understands the business flow but should not need to design a distributed runtime.

Therefore, the SDK should minimize the need for authors to invent execution patterns.

A good Fred agent authoring experience should feel like:

- declaring a business journey,
- selecting bounded capabilities,
- wiring typed inputs and outputs,
- configuring a few domain instructions,
- relying on the SDK for the rest.

A bad authoring experience is one where authors must decide on their own:

- what to do when a tool fails,
- how to retry,
- how to represent state transitions,
- how to shape model outputs,
- how to report progress,
- how to fall back safely.

---

## 6. Architectural Position

Fred SDK V2 should treat the language model as a **bounded subsystem**.

The model may be used for tasks such as:

- structured extraction,
- bounded classification,
- constrained text generation,
- summarization,
- synthesis over already computed results.

The model should not be the primary owner of:

- execution policy,
- failure handling,
- state progression,
- tool orchestration rules,
- compliance-sensitive behavior,
- observability semantics.

---

## 7. Authoring Model

Fred SDK V2 should expose a constrained authoring model with two main families.

### 7.1 Profile / ReAct-style agents

These support simple use cases where the business journey is short and tool usage is limited.

Typical properties:

- narrow scope,
- minimal state,
- bounded tool set,
- mostly linear interaction model.

These are appropriate when the SDK can provide most runtime behavior and the author only needs to declare:

- role,
- description,
- tools,
- options,
- bounded instructions,
- guardrails.

### 7.2 Workflow / Graph agents

These support more complex business journeys where execution should be explicit.

Typical properties:

- explicit state schema,
- explicit nodes,
- explicit transitions,
- deterministic control flow,
- clear terminal conditions.

These are appropriate when the business process matters more than conversational flexibility.

---

## 8. What Should Be Centralized in the SDK

The SDK should centralize the following concerns.

### 8.1 Tool error handling

Tool failure behavior must not be left to prompt wording.

The SDK should define standard patterns such as:

- fail fast,
- retry,
- degrade gracefully,
- ask for human choice,
- emit structured user-facing error,
- convert exception to typed state outcome.

### 8.2 Model output shaping

Authors should not manually parse free-form model outputs when structured outputs are possible.

Preferred pattern:

- schema-first,
- validated,
- typed,
- retry-capable at the SDK layer.

### 8.3 State transition semantics

Transitions should be explicit in code, not hidden in text instructions.

### 8.4 Human interaction patterns

When disambiguation is needed, authors should use standard SDK patterns for:

- choosing among options,
- confirming scope,
- cancelling safely.

### 8.5 Artifact lifecycle

Publishing files, links, or reports should follow a standard SDK flow.

### 8.6 Progress signaling

Runtime progress and status emission should be standardized, not improvised.

### 8.7 Safety defaults

The SDK should enforce safe defaults for:

- missing tool outputs,
- empty model outputs,
- cancelled interactions,
- malformed structured data,
- unavailable resources.

---

## 9. What Should Not Be Centralized Excessively

The SDK should not over-centralize the domain itself.

Authors must still control:

- business vocabulary,
- domain-specific instructions,
- domain schemas,
- business workflows,
- final user experience tone within safe bounds,
- domain-specific post-processing.

The SDK should constrain execution, not erase authorship.

---

## 10. Prompting: Important but Secondary

Prompt design remains useful, but it should not carry critical operational behavior.

A prompt may guide:

- tone,
- style,
- domain framing,
- response format,
- extraction objectives.

A prompt should not be the only place where the system defines:

- retry rules,
- failure semantics,
- state machine behavior,
- authorization decisions,
- routing guarantees.

The goal is not to eliminate prompts. The goal is to demote them from "hidden runtime logic" to "bounded behavioral input".

---

## 11. Examples from Current Fred Direction

### 11.1 Positive pattern: structured generation in a tool

The slide maker pattern is promising because it uses:

- explicit tool definition,
- structured extraction into `SlideContent`,
- explicit file resource loading,
- explicit artifact publishing,
- explicit error handling.

This is a good example of bounded model usage embedded in a deterministic tool flow.

### 11.2 Positive pattern: explicit workflow for SQL agent

The SQL graph pattern is promising because it separates:

- input/state,
- workflow definition,
- node behavior,
- terminal finalization.

This improves:

- readability,
- testability,
- business review,
- debugging.

### 11.3 Current caution

Even in well-structured flows, there is still a risk of leaking too much operational semantics into model prompts, especially around:

- intent routing,
- SQL drafting confidence,
- synthesis behavior,
- ambiguity handling.

The RFC direction is to continue moving those concerns toward typed SDK contracts and explicit execution policies.

---

## 12. Desired Author Experience

An author should ideally be able to say:

- "I want an agent that loads context, resolves scope, runs one operation, and returns a typed result."
- "If scope is ambiguous, ask the user with the standard choice UI."
- "If the tool fails, produce the standard error path."
- "Use a structured model call only for this classification step."
- "Publish the generated artifact with the standard Fred artifact API."

The author should not need to invent:

- an ad hoc state machine,
- custom retry loops,
- a prompt-based fallback protocol,
- their own observability semantics.

---

## 13. Consequences for SDK API Design

The SDK API should increasingly favor:

- declarative contracts over open-ended callbacks,
- typed outcomes over string conventions,
- explicit policies over prompt hints,
- bounded extension points over unrestricted flexibility.

Examples of desired evolution:

- standard tool invocation policies,
- explicit node outcome types,
- richer structured model APIs,
- first-class error taxonomy,
- shared finalization helpers,
- reusable built-in workflow patterns.

---

## 14. Testing Implications

A major reason for this direction is testability.

Fred agents should be testable at several layers:

### 14.1 Unit tests

- tools,
- nodes,
- helpers,
- schema validation.

### 14.2 Workflow tests

- state progression,
- route selection,
- terminal conditions,
- human choice handling.

### 14.3 Contract tests

- structured model contract,
- tool output contract,
- artifact publication contract.

### 14.4 Runtime behavior tests

- tool failure behavior,
- cancelled interaction behavior,
- empty retrieval behavior,
- malformed model output behavior.

The less behavior is hidden in prompts, the more meaningful these tests become.

---

## 15. Observability Implications

Even though observability is already a Fred concern, this RFC reinforces one key point:

> Good observability requires explicit semantics.

Observability becomes stronger when the SDK can distinguish clearly between:

- model invocation,
- tool execution,
- state transition,
- human choice request,
- finalization,
- recoverable failure,
- terminal failure.

This is easier when the SDK defines the execution vocabulary rather than letting each agent invent it.

---

## 16. Non-Goals

This RFC does not attempt to:

- remove language models from Fred,
- eliminate prompts,
- force every agent into a graph,
- replace domain expertise with framework rigidity,
- solve all alignment or hallucination problems.

The goal is narrower and more practical:

- reduce accidental fragility,
- guide authors toward reliable patterns,
- make production behavior more explicit.

---

## 17. Proposed Direction

Fred SDK V2 should continue toward:

1. **Constrained authoring primitives**
2. **Explicit business workflows**
3. **Schema-first model interactions**
4. **SDK-owned execution policies**
5. **Standardized error and finalization paths**
6. **Reduced dependence on prompt-defined operational logic**

---

## 18. Agent template taxonomy (decided 2026-05-22)

Fred distinguishes two categories of ReAct agents exposed in an agentic pod. This
distinction is user-facing and must be reflected in naming, UX, and documentation.

### 18.1 Generic assistant

One generic assistant per pod. It carries no pre-wired MCP servers and no
opinionated system prompt. Its purpose is to give operators a blank slate they can
configure freely at enrollment time: pick the tools they want from the full catalog,
write or import any system prompt.

Properties in code:

- `default_mcp_servers = ()` — no servers pre-selected
- `system_prompt_template` — minimal default, fully overridable via `prompts.system` FieldSpec
- all catalog servers are available for the operator to activate at enrollment

The `fred.github.assistant` (General-purpose assistant) is the canonical generic
assistant for the `fred-agents` pod.

### 18.2 Specialized templates

Specialized templates are ready-to-use agents pre-wired for a specific operational
domain. They come with:

- a non-empty `default_mcp_servers` tuple declaring the tools the template needs
- a curated default system prompt that the operator may override via FieldSpec
- a descriptive `role` string that communicates the template's domain clearly

The MCP servers declared by a specialized template are **locked**: they appear in
the Tools tab of the enrollment form but their toggle is read-only. The operator
can see which tools the template uses but cannot remove them. This is intentional:
the template's identity and correctness depend on its canonical tool set.

There is no extension mechanism. A specialized template is defined as-is. If an
operator needs a different combination of tools they should use the generic assistant
and configure it from scratch.

Examples in the `fred-agents` pod:

- `fred.github.sentinel` — Monitoring assistant, locked to OpenSearch MCP
- `fred.github.rag_expert` — Rico, locked to the built-in knowledge.search tool ref
- `fred.github.react_rag_mcp` — Document search assistant, locked to KF text-search MCP

### 18.3 User-chosen name

Both categories require the operator to provide a display name at enrollment time.
The template's `role` field is the catalog label (what the operator sees when
browsing templates). The `display_name` entered at enrollment becomes the instance's
identity within the team. These are two separate fields and must never be conflated.

### 18.4 Shared prompt bundles in libs

Some output conventions should be reusable across pods, not reimplemented
inside one application package. A current example is Mermaid-safe Markdown
generation for the chat renderer: every shipped default agent should follow the
same formatting rules so the frontend can render diagrams reliably.

Decision:

- The canonical location for cross-pod shared prompt fragments is a library
  package under `libs/`, with `fred-sdk` as the default authoring-facing
  surface.
- No heavy framework feature is required for this. The existing
  `fred_sdk.resources` Markdown loaders are already the right primitive; if one
  extra helper is needed it should stay small and live in `fred-sdk`, not in an
  application pod package.
- `load_agent_prompt_markdown(..., include_global_base_prompts=True)` is the
  preferred call-site for file-backed default system prompts. It appends the
  package-owned fragments from `fred_sdk.resources.prompts` while keeping agent
  modules focused on loading their own prompt file.
- `fred_sdk.apply_global_base_prompts(...)` remains the lower-level helper for
  inline or dynamically assembled prompts.
- A pod package may still add pod-local fragments, but it should do so by
  extending the shared library bundle rather than by becoming the canonical
  owner of cross-agent fragments.
- The shared bundle is **authoring-time composition of template defaults**. It
  is not a runtime injection layer and does not replace operator overrides.
- Shared prompt bundles are for cross-agent presentation or output conventions
  only.
- `fred-runtime` is not the home of these reusable fragments. Runtime remains
  responsible for mandatory execution-time instructions and contract-enforced
  injections.
- Tool-specific, non-negotiable behavior still belongs in runtime-enforced
  contracts such as MCP `agent_instructions`, not in shared prompt layers.

This keeps author ergonomics simple while preserving the architectural rule of
this RFC: prompts may shape presentation, but operational correctness should
move toward explicit SDK or runtime contracts whenever possible. In practice, a
pod shipped elsewhere should be able to import the same shared prompt bundle,
append one or two pod-local fragments, and benefit from the same renderer-
oriented defaults without depending on any application pod package.

### 18.5 Implementation contract for locked MCP servers

The `locked: bool = False` field on `MCPServerRef` (fred-sdk) marks a server as
non-toggleable. A locked server:

- appears in the Tools tab of the enrollment form
- has its toggle rendered as disabled (read-only, not greyed out)
- is always included in `selected_mcp_server_ids` regardless of operator input
- cannot be removed via `UpdateAgentInstanceRequest`

Specialized templates set `locked=True` on all their `MCPServerRef` entries.
The generic assistant declares no servers, so the question does not arise.

---

## 19. Open Questions

The following questions remain open and should guide implementation:

1. Which execution policies should be first-class in the SDK?
2. How much author freedom should remain in simple ReAct-style agents?
3. Should common workflow patterns become built-in templates?
4. What is the minimal error taxonomy Fred should standardize?
5. How should the SDK expose bounded model use without encouraging prompt-centric design?
6. Where should domain-specific flexibility end and runtime discipline begin?

---

## 19. Recommendation

Proceed with the current direction.

More precisely:

- keep strengthening typed, constrained SDK primitives,
- keep moving critical behavior from prompts into code and SDK contracts,
- keep favoring explicit workflow definitions for non-trivial agents,
- keep designing for authors who need safety and guidance more than raw freedom.

This is the most credible path for Fred if the objective is to support industrial-grade agents rather than demo-grade agents.

---

## 20. Final Statement

Fred SDK V2 should be understood as a framework for **authoring reliable agents under controlled execution**, not as a toolkit for composing prompt-driven improvisation.

Its success will come not from how much freedom it gives to agent authors, but from how effectively it prevents them from creating fragile systems by accident.
