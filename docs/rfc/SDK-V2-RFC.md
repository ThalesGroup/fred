# RFC: Fred SDK V2 for Industrial-Grade Agent Authoring

- Status: Draft
- Authors: Fred core team
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

## 18. Open Questions

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