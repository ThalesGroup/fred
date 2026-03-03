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

## 11. Honest Pros And Costs (Current Stage)

The practical trade-off is not theoretical anymore. It is visible in day-to-day
development.

Main benefits we get from v2:

- simpler ReAct authoring for product agents:
  - small tools + declarative definition
  - less runtime plumbing in each agent file
- stronger platform consistency:
  - one runtime contract for pause/resume, inspection, and structured outputs
  - one place to enforce behavior across all agents
- explicit decoupling from execution substrate:
  - LangChain/LangGraph can evolve underneath without rewriting authoring model
- shared observability baseline:
  - runtime-level spans and metadata conventions can be enforced centrally
  - teams debug with the same tracing vocabulary instead of ad hoc logs
  - ReAct model calls are traced by runtime under a standard span name (`v2.react.model`)

Main costs we accept with v2:

- runtime ownership tax:
  - Fred must maintain contracts that framework users get “for free”
- observability ownership tax:
  - if instrumentation is missing in Fred runtime, Langfuse analysis degrades
  - we must actively maintain span coverage and naming quality
- migration tax:
  - legacy `AgentFlow` agents need deliberate porting and retesting
- capability curation tax:
  - we must decide when to elevate recurring MCP usage into first-class tool refs

How we keep those costs under control:

- keep agent authoring small and declarative; move runtime complexity into shared layer
- enforce runtime span taxonomy in code review and tests
- treat “instrumentation_gap” as a product bug, not as optional tech debt
- avoid creating new runtime models for business variants that can be solved by profiles

## 11.1 Current ReAct Verdict (v1 vs v2)

For product ReAct agents, the current v2 position is now clearer:

- v1 style (agent-local `create_agent` composition) gives flexibility, but observability quality depends on each agent implementation.
- v2 ReAct centralizes runtime instrumentation and trace metadata conventions in one shared layer.
- This gives a more reliable baseline in Langfuse across agents (`agent_name`, `team_id`, `user_name`, `fred_session_id`) and runtime-owned model spans (`v2.react.model`, `operation=model_call`).
- trade-off remains: if runtime instrumentation regresses, impact is platform-wide. This is why instrumentation quality must be treated as a runtime release criterion.

So yes: for operated product agents, v2 ReAct is the cleaner and safer default than v1-style per-agent runtime wiring.

## 12. Pragmatic Decision Rule

Use plain framework patterns directly when:

- the scope is local, short-lived, and not a platform concern
- no shared pause/resume, inspect, or policy semantics are required

Use Fred v2 runtime when:

- the agent is a product capability operated by multiple teams
- governance, HITL, structured outputs, and durable continuity matter
- you want common behavior, common observability, and cleaner future adapter swaps

That is the real criterion.
Not “is middleware useful?” but “do we need a governed runtime contract?”
