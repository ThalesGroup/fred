# GenAI SDK Spec

This document summarizes the approach proposed in `genai-sdk/` and provides a first gap analysis for adoption in Fred.

Important framing update:

- Fred now has a real v2 runtime model (`ReActRuntime`, `GraphRuntime`)
- so the question is no longer "should genai-sdk replace Fred runtime?"
- the real question is "where can genai-sdk complement Fred below the runtime boundary?"

It is not a statement that Fred should replace its current runtime with this SDK.
The proposal is better understood as a portable capability layer around agents.

Primary source material reviewed:

- `genai-sdk/README.md`
- `genai-sdk/docs/architecture/architecture.md`
- `genai-sdk/docs/architecture/getting-started.md`
- the ADRs under `genai-sdk/docs/adrs/`
- the package surfaces under `genai-sdk/packages/`

## 1. Executive Summary

The proposed GenAI SDK is a thin, modular, contract-first toolkit for standardizing the infrastructure around agents:

- request context and correlation
- token acquisition and token exchange
- observability and tracing
- tool invocation contracts
- transport abstraction
- registry-based tool discovery
- optional LangGraph and LangChain glue

The key architectural idea is:

- the SDK should standardize capabilities around agents
- it should not define a monolithic agent runtime
- frameworks such as LangGraph and LangChain are adapters, not the core

This is a strong approach for platform convergence.
It aligns well with the goal that an agent useful on platform A should also be portable to Fred, or vice versa, with minimal rewiring of cross-cutting concerns.

## 1.1 Where Fred Already Converges

Fred v2 already moved in a compatible direction on several points:

- pure `AgentDefinition` authoring model
- platform-owned runtime lifecycle
- explicit runtime services (`chat_model_factory`, `tool_invoker`, `tool_provider`)
- safe `inspect` endpoint separated from activation
- structured runtime events
- structured UI outputs such as `GeoPart` and `LinkPart`

This matters because it means future compatibility work should start from the current v2 contracts, not from legacy `AgentFlow`.

## 2. Core Design Philosophy

The proposal is built around a few explicit principles:

- contracts are the authority
- runtime implementations are replaceable
- framework glue is optional
- behavior should be visible and explicit, not hidden by a large framework

In practical terms, the SDK tries to avoid this anti-pattern:

- "portable agent" actually means "agent locked into one framework runtime"

Instead, it defines a portable spine made of:

- canonical request context
- stable tool invocation envelope
- standard tracing taxonomy
- standard identity interfaces
- standard registry descriptor model

That is the strongest part of the proposal.

## 3. What The SDK Is And Is Not

### What it is

- a shared contract layer
- a set of thin interfaces and implementations
- a tool invocation stack with middleware
- optional glue for LangGraph and LangChain
- a testkit for conformance without lock-in

### What it is not

- not a hosted platform
- not a full agent framework
- not a replacement for an existing orchestrator such as Fred
- not a governance engine by itself

This distinction matters.
Fred already has an agent runtime and lifecycle model.
The SDK is most valuable below that layer, not above it.

## 4. Architectural Model

The proposal can be summarized as a layered model.

### Layer 1: Contracts

Authoritative contracts live in JSON schemas and mirrored Pydantic models.

Main models:

- `Context`
- `ToolCallEnvelope`
- `ToolDescriptor`
- `NormalizedError`
- `TelemetryMetadata`

These are intended to be stable and framework-agnostic.

### Layer 2: Core interfaces

The core package defines small protocols, mainly:

- `TokenProvider`
- `TokenExchangeProvider`
- `Tracer`
- `RegistryClient`
- `ToolClient`
- `ToolTransport`

The important design choice is that these interfaces are intentionally small.
That makes them easy to adapt to an existing platform.

### Layer 3: Implementations of cross-cutting concerns

The SDK then provides concrete modules for:

- observability
- identity
- registry
- transport
- tool invocation middleware

These are still meant to be replaceable.

### Layer 4: Optional framework glue

The LangGraph and LangChain packages are explicitly outside the core.

That means:

- the SDK does not require LangGraph
- the SDK does not require LangChain
- if those frameworks are replaced later, the contract spine remains valid

This is architecturally sound.

## 5. Main Concepts

### 5.1 Canonical Context

The SDK defines a portable `Context` model that carries:

- `request_id`
- `correlation_id`
- `trace_id`
- `actor`
- `tenant`
- `environment`
- optional client and agent metadata
- optional non-sensitive baggage

This context is meant to flow across:

- client
- agent
- registry
- tool invocation
- observability

This is not the same thing as Fred `RuntimeContext`.

The SDK `Context` is deliberately narrow and portable.
Fred `RuntimeContext` is richer and includes session-scoped application concerns such as:

- selected libraries
- selected documents
- language
- search scope
- attachments
- access token and refresh token

So the correct reading is:

- SDK `Context` is the portable cross-platform envelope
- Fred `RuntimeContext` is the local runtime state object

### 5.2 Tool Invocation As The Main Portable Boundary

The proposal centers a single tool invocation API:

- `ToolClient.invoke(tool_ref, input, ctx)`

That is a strong choice.
It means the stable portability boundary is not:

- a LangChain tool object
- a LangGraph node
- a platform-specific MCP runtime

It is:

- a tool reference
- a normalized input payload
- a portable context

This is where Fred can benefit the most.

### 5.3 Middleware-Based Cross-Cutting Concerns

The invocation layer composes concerns via middleware:

- error normalization
- registry resolution
- tracing
- context header propagation
- auth
- retry
- timeout
- idempotency
- optional redaction

This is one of the best aspects of the design.
It gives a precise place to put enterprise concerns without contaminating agent code.

### 5.4 Registry As Enrichment And Discovery

The registry model standardizes:

- tool discovery
- lookup by reference
- small in-memory caching
- normalized descriptors

This is useful for portability, observability, and future governance.

However, in the current implementation, registry resolution is mostly enrichment.
It does not yet fully control transport routing across multiple endpoints.

### 5.5 Observability As A First-Class Concern

The SDK standardizes tracing around a small taxonomy:

- `agent.run`
- `llm.call`
- `tool.call`
- `registry.query`
- `gateway.invoke`

It also introduces a minimal tracer interface and simple implementations:

- null tracer
- logging tracer
- in-memory tracer

This is a good design because it decouples span semantics from any one backend.

### 5.6 Identity As A Replaceable Service

Identity is modeled as provider interfaces:

- token acquisition
- optional token exchange

This is a sensible enterprise design because it separates:

- how a token is obtained
- from where it is used

It also avoids tying transport code directly to a specific OAuth flow.

### 5.7 Framework Glue Is Optional

The LangGraph and LangChain packages do not redefine the SDK.
They just adapt it.

LangGraph glue provides:

- context injection
- wrapped node spans
- tool nodes backed by `ToolInvocationClient`

LangChain glue provides:

- context propagation helpers
- tool wrappers backed by `ToolInvocationClient`
- callback-based tracing hooks

This is the correct architectural direction.

## 6. The Intended Operating Model

The intended end-to-end flow is roughly:

1. Build or receive a canonical SDK `Context`
2. Agent logic decides to call a tool by reference
3. Tool call goes through `ToolInvocationClient`
4. Middleware applies auth, tracing, header propagation, registry enrichment, and error normalization
5. Transport executes the call through MCP or another backend
6. Result is returned in a transport-agnostic way

The major consequence is:

- agent code should stop owning most infrastructure concerns directly

That is exactly the kind of convergence goal Fred should care about.

## 7. Why This Is Interesting For Fred

Fred already has good answers for:

- agent lifecycle
- session-aware runtime context
- caching warm agents
- LangGraph execution
- MCP runtime management
- KPI instrumentation
- chat-oriented persistence and restore

What Fred does not currently standardize in a cross-platform way is:

- canonical portable context
- portable tool invocation contract
- standardized token-provider abstraction
- standardized portable tracing model around tools and graph nodes

This is where `genai-sdk` fits well.

The best mental model is:

- Fred keeps the agent runtime shell
- GenAI SDK provides portable capabilities underneath it

## 8. First Gap Analysis

This section is intentionally a first-pass analysis, not a final migration plan.

### Gap 1: The SDK is capability-oriented, Fred is runtime-oriented

Fred today is centered on:

- `AgentDefinition`
- `AgentFactory`
- `RuntimeContext`
- `ReActRuntime`
- `GraphRuntime`
- `MCPRuntime`

Legacy `AgentFlow` still exists, but it is no longer the best architectural reference point.

The SDK is centered on:

- contracts
- small interfaces
- middleware
- transport-agnostic tool invocation

This is not a contradiction, but the layering is different.

Implication:

- Fred should not try to replace its v2 runtime model with the SDK
- Fred should integrate the SDK below the agent lifecycle layer

### Gap 2: SDK `Context` is not rich enough to replace Fred `RuntimeContext`

Fred `RuntimeContext` carries many application-specific values that do not belong in a cross-platform standard context.

Examples:

- selected document libraries
- selected documents
- search scope
- attachments markdown
- deep search toggle
- language
- live session id

Implication:

- Fred needs an adapter from `RuntimeContext` plus request/session metadata into SDK `Context`
- both context models should coexist

### Gap 3: The SDK is currently sync-first, Fred is async-first

Most SDK interfaces are synchronous:

- tool invocation
- token providers
- registry client
- transports

The LangGraph async integration currently uses `asyncio.to_thread(...)` for sync invocation.

Implication:

- this is fine for pilots and narrow adoption
- it is not ideal as the final shape for Fred's main runtime path

This is probably the most important technical gap in the current implementation.

### Gap 4: Registry resolution is not yet full routing

The registry resolves a `ToolDescriptor` and enriches the envelope.
But the MCP transport still targets the transport's configured endpoint directly.

Implication:

- current registry support is useful for discovery and tracing
- it is not yet a complete answer for multi-server execution routing

Fred's current MCP runtime already handles multi-server concerns more concretely.

### Gap 5: The identity model does not directly match Fred's user-token model

The SDK identity package is well-structured, but its stock implementations are mainly:

- client credentials
- token exchange

Fred often needs:

- current user token from runtime
- token refresh on expiry
- MCP calls in user context

Implication:

- Fred should implement its own SDK-compatible token provider rather than adopt the stock provider as-is

### Gap 6: Observability models differ

Fred today mixes:

- Langfuse callbacks
- KPI timers and counters
- structured logging

The SDK proposes:

- a single small tracer abstraction
- standard span names and attributes

Implication:

- there is good alignment at the conceptual level
- Fred needs an adapter layer, not a wholesale rewrite

### Gap 7: Fred MCP integration is richer than the current SDK MCP layer

Fred's `MCPRuntime` already handles:

- multi-server setup
- runtime token handling
- retry interceptor for expired tokens
- in-process and remote tools
- tool-node integration

The SDK MCP transport is cleaner and more portable, but currently simpler.

Implication:

- short term, Fred should wrap its existing MCP behavior behind SDK-style interfaces
- not replace it immediately

### Gap 8: The SDK does not define agent lifecycle semantics

This is by design.
It is a strength, not a weakness.
But it means it does not answer questions such as:

- when agents are built
- when runtime is activated
- how sessions are cached
- how graph inspection works without activation

Fred already has those semantics.

Implication:

- Fred lifecycle remains authoritative
- SDK capability integration should happen inside that lifecycle

## 9. Recommended Adoption Strategy For Fred

The right adoption path is incremental.

### Step 1: Introduce SDK Context alongside Fred RuntimeContext

Create a small adapter that derives portable SDK `Context` from:

- request identifiers
- user identity
- tenant
- environment
- agent id
- session correlation information

This should be injected into LangGraph and LangChain execution config without disturbing Fred's existing runtime context.

### Step 2: Add a Fred tracer adapter

Implement the SDK `Tracer` protocol on top of Fred's current observability stack.

This lets Fred emit standardized spans while preserving:

- Langfuse
- KPI metrics
- current logs

### Step 3: Add a Fred token provider adapter

Implement an SDK-compatible token provider that uses:

- `RuntimeContext.access_token`
- Fred token refresh logic
- optional user-context or service-context strategies

This is the cleanest way to align identity concerns without losing Fred behavior.

### Step 4: Introduce a Fred tool invocation client path

Wrap Fred MCP execution behind SDK-style invocation interfaces so that one tool path can be exercised through:

- canonical context
- middleware
- standardized tracing
- standardized error normalization

This is the highest-value real integration point.

### Step 5: Pilot on one or two agents

Start with:

- one academy agent
- or one narrow production agent with a limited tool surface

The goal should be validation of the seam, not full migration.

### Step 6: Add contract-style tests

Adopt the testkit mindset:

- assert context propagation
- assert tool-call envelopes
- assert normalized error mapping
- assert expected spans are emitted

This is essential if the real goal is platform portability.

## 10. Preliminary Recommendation

The proposed SDK is architecturally sound for the stated convergence goal.

Its strongest ideas are:

- contract-first design
- transport-agnostic tool invocation
- optional framework glue
- explicit middleware for enterprise concerns
- testkit-based conformance rather than lock-in

Its main current weaknesses are:

- sync-first runtime shape
- incomplete registry-to-routing story
- an identity layer that does not yet directly express Fred's live user-token model
- less MCP sophistication than Fred's current runtime

The practical conclusion is:

- Fred should not adopt the SDK as a runtime replacement
- Fred should adopt it as a portable infrastructure layer around agents

That is where the designs are complementary.

## 11. Bottom Line

If the organizational objective is cross-platform agent portability, the `genai-sdk` proposal is going in the right direction.

The best way for Fred to leverage it is not:

- "rewrite Fred around this SDK"

It is:

- "let Fred remain the runtime, and let the SDK become the portable capability contract around it"

That approach preserves Fred's strengths while moving the organization toward convergence.
