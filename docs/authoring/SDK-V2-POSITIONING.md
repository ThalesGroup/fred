# SDK V2 Positioning: Helping Agent Authors Avoid Industrial Catastrophes

Fred SDK V2 is being designed around a simple conviction:

> Building an agent should not require every author to become an expert in orchestration, failure semantics, runtime discipline, and model behavior.

That is the job of the SDK.

Too many agent frameworks make it easy to produce an impressive demo and too easy to produce a fragile system. The danger does not come only from hallucinations. It comes from hidden behavior, inconsistent execution patterns, and the fact that critical agent logic is often scattered across prompts, callbacks, and ad hoc orchestration code.

Fred takes a different path.

## The real problem is not "how to call an LLM"

The real problem is how to help authors create agents that remain understandable, testable, and maintainable when they leave the lab and enter real environments.

In practice, industrial failures often come from problems like these:

- tool failures handled differently from one agent to another,
- implicit control flow hidden in prompts,
- weakly structured outputs,
- difficult debugging,
- business logic mixed with generation logic,
- excessive author freedom with too few safety rails.

Fred SDK V2 is designed to reduce these risks.

## Agent authors need protection, not just flexibility

Many frameworks are built primarily for developers who are comfortable wiring graphs, prompts, retries, and custom state handling by hand.

Fred is increasingly designed for **agent authors**: people who understand a business process and want to express it safely without having to invent a runtime architecture from scratch.

That means the SDK should provide:

- constrained authoring patterns,
- typed contracts,
- standard tool behavior,
- explicit workflow primitives,
- built-in execution discipline.

This is not about making agents less capable. It is about making them more reliable.

## Fred does not reject language models. It contains them.

Fred does not treat the model as the full system. It treats it as one component inside a larger, controlled runtime.

This matters because language models are powerful for some tasks and weak for others.

They are valuable for:

- structured extraction,
- bounded classification,
- synthesis,
- controlled generation.

They are poor foundations for:

- execution policy,
- error semantics,
- orchestration guarantees,
- safety-critical branching.

Fred SDK V2 is therefore moving toward a model where the runtime owns the operational behavior, and the model contributes only where it is genuinely useful.

## The goal is to remove accidental fragility

A good agent SDK should not simply expose powerful primitives. It should make the safe path the natural path.

In Fred, that means reducing the amount of behavior that authors must improvise themselves.

Authors should not need to decide from scratch:

- how a tool exception becomes a user-facing response,
- how to retry a failed step,
- how to structure model outputs,
- how to publish an artifact,
- how to ask the user to disambiguate a choice,
- how to finalize a workflow safely.

These are platform concerns. The SDK should own them.

## Explicit workflows when the business journey matters

Fred already supports simple profile-style agents for narrow use cases. But as soon as the business journey becomes important, explicit workflows become necessary.

This is why workflow-shaped agents are central to the Fred direction.

A well-formed workflow gives:

- explicit state,
- explicit steps,
- explicit transitions,
- explicit terminal behavior.

This is not just a technical preference. It is what makes agents reviewable by architects, maintainers, and security-minded teams.

## Prompts still matter, but they should stop carrying the system

Prompting is still useful in Fred, but it should not be the hidden place where critical system behavior lives.

Prompts are appropriate for:

- style,
- tone,
- domain framing,
- extraction instructions,
- bounded generation goals.

They are not a sound basis for:

- failure handling,
- routing guarantees,
- runtime policies,
- compliance behavior.

Fred's direction is therefore not "prompt engineering first". It is "runtime discipline first".

## What makes this industrial

Fred SDK V2 is not trying to optimize for the shortest path to a demo. It is trying to optimize for the long-term cost of ownership of an agent system.

That includes:

- maintainability,
- explicitness,
- testability,
- observability,
- reproducibility,
- safer evolution over time.

An industrial platform should not depend on every individual author making perfect decisions. It should make common mistakes harder to commit.

## Why this matters for open source

Open source agent projects often face a difficult tradeoff:

- either expose low-level flexibility and let users assemble fragile systems,
- or impose stronger patterns and guide users toward robustness.

Fred chooses the second path deliberately.

This is important because Fred is not trying to be only a playground for experimentation. It is trying to become a credible foundation for real agentic applications, including in constrained and demanding environments.

## The Fred promise

Fred SDK V2 aims to give authors a better deal:

- less accidental complexity,
- fewer hidden behaviors,
- more explicit execution,
- more reusable patterns,
- safer defaults,
- stronger contracts.

In short:

> Fred helps authors express business intent while the SDK takes responsibility for operational discipline.

That is how agent platforms become sustainable.