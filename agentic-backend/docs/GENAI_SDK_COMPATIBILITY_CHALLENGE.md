# Fred v2 ↔ GenAI SDK Compatibility Challenge

This document is not an adoption plan.
It is a challenge checklist meant to prevent naive convergence work.

For the more specific question of how Fred v2 relates to LangChain middleware,
see [RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](./RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md).

The question is not:

- "can Fred import a few SDK interfaces?"

The real question is:

- "does Fred v2 already expose the right boundaries so a `genai_sdk`-style substrate can complement it without flattening important platform behavior?"

## 1. Current Position

Fred now has a real v2 runtime model:

- `ReActAgentDefinition` + `ReActRuntime`
- `GraphAgentDefinition` + `GraphRuntime`
- safe `inspect` endpoint
- explicit runtime services
- structured runtime events
- structured UI outputs (`GeoPart`, `LinkPart`, sources)

This is good news.
It means compatibility work should start from the v2 contracts, not from legacy `AgentFlow`.

## 2. The Boundary We Want

The clean target is:

- Fred owns authoring contracts and runtime semantics
- a future `genai_sdk`-style layer standardizes cross-cutting capabilities below that

So the intended layering is:

1. Fred authoring SDK
   - `AgentDefinition`
   - `ReActPolicy`
   - `GraphDefinition`
   - inspection

2. Fred runtime platform
   - bind / activate / execute / stream / resume

3. Capability substrate
   - context propagation
   - tracing
   - token exchange
   - tool invocation transport
   - registry/discovery

This means `genai_sdk` should complement Fred below the runtime, not replace it.

## 3. What Already Aligns Well

These Fred v2 pieces are already close to the shape we want:

- `PortableContext` / bound runtime context split
- `RuntimeServices`
- `ToolInvokerPort`
- `ToolProviderPort`
- explicit runtime events
- explicit structured outputs
- safe non-activating inspection

These are the strongest convergence points.

## 4. What Must Be Challenged Hard

Before moving toward `genai_sdk`, Fred should challenge these areas explicitly.

### 4.1 Tool invocation boundary

Question:

- is `ToolInvokerPort` the real long-term portability boundary?

What to verify:

- tool ref stability
- normalized input/output shape
- middleware compatibility
- error normalization
- support for structured UI parts and sources

Risk:

- if tool outputs remain too Fred-specific, the compatibility layer becomes superficial

### 4.2 Runtime-provided tools

Question:

- how should dynamic MCP tools fit into a registry- or transport-oriented SDK view?

What to verify:

- runtime discovery vs declared capability
- naming stability
- duplicate/conflicting tool names
- partial failure behavior

Risk:

- Fred may still rely too much on local runtime conventions instead of explicit discovery contracts

### 4.3 HITL

Question:

- can HITL be expressed as a stable platform capability rather than a LangGraph-era mechanism?

What to verify:

- typed human input request/response
- checkpoint ownership
- resume semantics
- compatibility with ReAct and Graph

Risk:

- if HITL remains too tied to runtime internals, it will be hard to map cleanly to a portable capability layer

### 4.4 Structured UI outputs

Question:

- are `GeoPart`, `LinkPart`, and similar outputs first-class enough?

What to verify:

- clear separation between model text and UI intent
- serialization stability
- transport neutrality

Risk:

- if these are treated as ad hoc frontend conveniences, Fred loses an important part of its differentiated runtime contract

### 4.5 Graph authoring contract

Question:

- is `GraphAgentDefinition` rich enough to be a true author-facing SDK, not only a structural preview model?

What to verify:

- executable node contract
- typed state transitions
- runtime service access
- structured outputs
- HITL support

Risk:

- if graph authoring is too weak, authors will fall back to LangGraph directly and the SDK boundary collapses

## 5. Immediate Questions To Test In Practice

These are the concrete questions Fred should keep answering through code, not opinion.

1. Can a real business ReAct agent be expressed without leaking runtime mechanics into the author class?
2. Can a real business workflow graph be expressed without falling back to raw LangGraph authoring?
3. Can MCP, HITL, and structured UI parts survive through the runtime boundary as first-class capabilities?
4. Can inspection stay pure while execution stays powerful?
5. Can all of that remain compatible with a future SDK-style capability substrate below the runtime?

## 6. Decision Gates Before Any Naive Adoption

Fred should not move from "interesting SDK" to "real compatibility effort" unless these gates are satisfied.

### Gate A: ReAct parity is preserved

Fred must still be able to express, execute, and inspect:

- MCP-backed agents
- tool approval
- structured sources
- structured UI parts

If an SDK mapping weakens those, the mapping is wrong.

### Gate B: Graph workflows remain first-class

Fred must still be able to express:

- typed workflow state
- deterministic routing
- richer HITL checkpoints
- structured outputs such as `GeoPart` and `LinkPart`

If an SDK integration forces authors back to raw LangGraph or framework glue, the authoring boundary failed.

### Gate C: Inspection stays pure

Fred must keep:

- non-activating `inspect`
- preview as informational artifact only
- no accidental dependency on runtime compilation for UI structure

If a future SDK assumption pressures Fred to inspect through execution, that is a regression.

### Gate D: Runtime ownership stays in Fred

Fred must keep ownership of:

- bind / activate / execute / resume
- session restore
- checkpoint lifecycle
- chat transport semantics

If an SDK layer starts redefining those semantics, it is overstepping the intended boundary.

## 7. Suggested Compatibility Work Order

If Fred wants to explore `genai_sdk` seriously, the work order should be:

1. stabilize Fred v2 contracts first
2. identify which runtime services map cleanly to SDK interfaces
3. challenge missing pieces explicitly
4. only then build adapters

The order should not be:

1. import SDK concepts
2. rename local classes
3. hope the semantics line up later

## 8. Concrete Near-Term Mapping Candidates

The most plausible early mapping targets are:

- `PortableContext` ↔ SDK context envelope
- `TracerPort` ↔ SDK tracer
- `ToolInvokerPort` ↔ SDK tool invocation client
- `ToolProviderPort` ↔ runtime discovery bridge
- token provider / refresh handling

These are good candidates because they do not force Fred to abandon its own runtime semantics.

## 9. What Fred Should Explicitly Challenge In genai_sdk

Fred should challenge the SDK on these concrete topics before trusting it as a substrate:

- can it carry structured UI outputs without flattening them into text?
- can it express HITL as a true capability instead of a framework callback?
- can it accommodate runtime-provided MCP tools, not only statically declared tools?
- can it preserve async-first execution without thread-wrapping the main path?
- can it live below a platform-owned runtime instead of trying to become the runtime?

If the answer is "not yet", that is acceptable.
But Fred should record those mismatches explicitly instead of papering over them with adapters.

## 10. Non-Goals For Now

Fred should explicitly avoid these shortcuts for now:

- replacing `AgentDefinition` with an SDK-native authoring model
- exposing framework internals directly again
- treating inspection preview as executable truth
- collapsing runtime-provided tools and declared tools into one vague concept

## 11. Success Criteria

Compatibility work should be considered successful only if:

- Fred keeps its v2 authoring clarity
- runtime semantics remain owned by Fred
- structured outputs and HITL stay first-class
- adapters to a future SDK reduce platform coupling instead of hiding it

That is the standard to judge future work against.
