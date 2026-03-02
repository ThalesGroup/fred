# Fred v2 Runtime vs LangChain Middleware

Status: stable architecture position

Audience: developers asking a fair question:

> Why did Fred build a v2 runtime instead of “just using LangChain middleware”?

Short answer:

- LangChain middleware is useful
- Fred v2 is not competing with it
- Fred v2 owns the governed runtime semantics that middleware does not solve

So the right framing is not:

- “Fred reinvented LangChain”

The right framing is:

- “Fred defines a platform runtime above the execution framework, and middleware
  can still live underneath that runtime”

## 1. The Misleading Question

The question “why did we reinvent all that?” sounds natural, but it mixes two
different layers:

1. a framework execution technique
2. a product/runtime contract

LangChain middleware belongs mostly to the first layer.
Fred v2 belongs mostly to the second.

That is why the overlap is smaller than it first appears.

## 2. What LangChain Middleware Is Good At

LangChain middleware is a good fit for local cross-cutting concerns around model
or tool execution.

Typical examples:

- tracing
- retries
- auth/header injection
- request enrichment
- response normalization
- local policy checks before a tool call

These are real needs. Fred should not reject them.

They are especially relevant under:

- `ToolInvokerPort`
- model invocation
- future SDK-backed transport layers

## 3. What Fred v2 Owns That Middleware Does Not

Fred v2 is responsible for the things that make an agent feel like a governed
service, not just a wrapped tool loop.

That includes:

- authoring contracts:
  - `ReActAgentDefinition`
  - `GraphAgentDefinition`
- safe introspection:
  - `inspect`
- business starting points:
  - ReAct profiles
- runtime-owned capabilities:
  - MCP defaults
  - HITL
  - structured outputs like `GeoPart` and `LinkPart`
  - resource fetching
  - artifact publishing
- pause/resume semantics
- checkpoint identity
- session continuity across turns
- adapter-safe execution for WebSocket today and Temporal later

Middleware does not naturally answer those questions.

## 4. The Practical Difference

Middleware helps answer:

- “how should this one model or tool call be wrapped?”

Fred v2 answers:

- “what kind of service is this agent?”
- “how should it pause, resume, inspect, and preserve business meaning?”
- “what is the stable authoring contract for developers?”

That is why Fred v2 is closer to a governed runtime platform than to a
middleware stack.

## 5. The Layering We Want

The healthy target stack looks like this:

1. Fred authoring layer
   - definitions
   - profiles
   - policies
   - graph structure

2. Fred runtime layer
   - bind
   - activate
   - execute
   - stream
   - pause/resume
   - inspect

3. Execution substrate
   - LangChain / LangGraph
   - middleware
   - tool transport
   - tracing
   - auth

This is the key point:

- middleware should sit **under** the Fred runtime contract
- not replace the Fred runtime contract

## 6. A Small Concrete Example

This is the kind of layering Fred v2 is aiming for.

```python
from agentic_backend.core.agents.v2 import (
    ReActAgentDefinition,
    ReActPolicy,
    ReActRuntime,
    RuntimeServices,
    ToolRefRequirement,
)


class OpsAssistant(ReActAgentDefinition):
    agent_id = "ops.assistant"
    role = "Operations assistant"
    description = "Helps investigate platform issues."
    tool_requirements = (
        ToolRefRequirement(tool_ref="logs.query"),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template="Investigate the issue, then answer clearly."
        )


# Under Fred, the tool invoker could later be backed by middleware:
# tracing, auth propagation, retries, registry lookup, etc.
services = RuntimeServices(
    tool_invoker=my_tool_invoker,
    chat_model_factory=my_model_factory,
)

runtime = ReActRuntime(
    definition=OpsAssistant(),
    services=services,
)
```

What this example shows:

- the agent author does not write middleware
- the author does not manage LangGraph directly
- the runtime still remains free to use middleware underneath `tool_invoker`

So middleware is still useful, but it is not the author-facing abstraction.

## 7. Where The Difference Becomes Obvious

The difference is easiest to see with graph agents.

Consider a workflow like the postal demo:

- identify the right parcel
- gather postal and IoT context
- show a map
- ask for a human decision
- reroute or reschedule
- remember the selected parcel next turn

This requires:

- typed workflow state
- deterministic routing
- explicit HITL checkpoints
- durable resume semantics
- structured UI outputs
- cross-turn memory policy

That is not just middleware.
That is runtime semantics.

## 8. Why This Matters For `genai_sdk`

This is exactly why Fred v2 is a good direction for convergence with a future
`genai_sdk`-style substrate.

The clean split is:

- Fred owns authoring and runtime semantics
- an SDK-style layer standardizes cross-cutting capabilities below that

So if a future SDK gives:

- tool invocation middleware
- auth propagation
- tracing
- registry lookup

that is valuable.

But Fred should still own:

- `ReActAgentDefinition`
- `GraphAgentDefinition`
- `inspect`
- HITL semantics
- checkpoint semantics
- structured business outputs

Otherwise Fred would stop being a platform and collapse back into framework glue.

## 9. The Real Benefit Of Fred v2

The main benefit is not “more abstraction”.

The main benefit is:

- a stable developer contract
- a governed runtime
- clear business semantics
- safer future adapters

That is what makes Fred v2 more than a nicer wrapper around LangChain.

## 10. Bottom Line

Fred v2 and LangChain middleware are complementary.

Use middleware for:

- local execution concerns
- transport concerns
- tracing/auth/retry enrichment

Use Fred v2 runtime for:

- what the agent is
- how it behaves as a service
- how it pauses, resumes, inspects, and preserves business meaning

That is why building Fred v2 was not a wasteful duplication.
It was the step needed to move from “agent code on top of a framework” to a
safer, more governed runtime platform.
