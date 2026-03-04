# Why A Parcel Operations Agent Is Better Served By A Graph Than By ReAct

This document explains a product decision, not a framework preference.

The question is not:

- "is ReAct good?"

The real question is:

- "for a customer-facing parcel operations role, what execution model best serves the business promise?"

The concrete reference case is the v2 parcel demo agent in [postal_tracking.py](/home/dimi/run/reference/fred/agentic-backend/agentic_backend/agents/v2/demos/postal_tracking/agent.py).

## 1. Start From The Business Role

The agent is not a generic assistant with access to some tools.

It has a narrow and meaningful business role:

- understand a question about *my* parcel
- identify the right parcel for *me*
- explain what is happening
- show operational context when useful
- display a map when useful
- ask for approval before a customer-impacting action
- perform a reroute safely
- confirm the outcome

That role matters.

A user does not experience this agent as "an LLM that can call tools".
They experience it as a service operator acting on a delivery.

That changes the right architecture.

## 2. Why ReAct Feels Attractive At First

ReAct is attractive because it is simple to author:

- give the model a prompt
- expose tools
- let it decide what to call
- let it answer naturally

For broad assistants, this is often the right choice.

For example:

- a general assistant
- a search copilot
- a log diagnosis helper
- an internal support agent with many possible directions

In those cases, flexibility is more valuable than strict orchestration.

## 3. Why That Same Flexibility Becomes A Business Liability Here

For parcel operations, the problem is not only "answering well".
It is "acting consistently, safely, and explainably on a customer process".

In this role, several business expectations are non-negotiable:

- The agent must operate on the right parcel.
- The agent must not silently choose the wrong parcel when several exist.
- The agent must not reroute a parcel without an explicit customer decision.
- The agent must gather the right operational context before proposing an action.
- The agent must remain understandable to product owners, operations teams, and customers.

These are not mere technical details.
They are part of the service contract.

If the model is left too free, the business risks become obvious:

- it may skip parcel disambiguation
- it may jump too fast to action
- it may call tools in the wrong order
- it may answer from partial context
- it may be harder to explain why an action was proposed or executed

For a business workflow, that is not "creative flexibility".
That is process drift.

## 4. What A Graph Gives The Business

A graph is valuable here because it turns the business journey into an explicit service path.

In plain business terms, the graph says:

1. First understand the request.
2. Then identify the parcel.
3. Then collect the relevant context.
4. Then either explain the situation or prepare an action.
5. If an action is needed, ask for approval.
6. Only then execute the action.
7. Finally summarize the result.

This matters because it gives the business four things that ReAct alone does not guarantee as strongly.

### 4.1 Predictable customer handling

The same type of request follows the same type of journey.

That means:

- fewer surprises in demos
- fewer surprises in production
- easier QA
- easier support

### 4.2 Safer action boundaries

The graph makes it explicit where a customer-impacting action can happen.

That means:

- approval can be mandatory at the correct step
- reroute logic can remain auditable
- sensitive actions are not mixed with general conversation flow

### 4.3 Better separation of "understanding" and "execution"

The model still plays an important role, but in the right place:

- to understand the request
- to synthesize operational context
- to communicate clearly

It does not own the whole workflow.

The workflow itself remains a business asset.

### 4.4 Better alignment with real service operations

Parcel operations are not an open-ended chat problem.

They are closer to:

- triage
- qualification
- context gathering
- decision support
- gated execution

That is a workflow shape.
A graph fits that shape naturally.

## 5. The Important Distinction: Intelligence Is Still Present

Choosing a graph does **not** mean choosing a rigid if/else bot.

The correct model is:

- use the model where interpretation or synthesis adds value
- use the graph where business sequencing matters

In the parcel demo, this means:

- the request can be classified semantically, not by crude keyword matching
- summaries can still be natural and useful
- the graph simply ensures that business-critical steps happen in the right order

So this is not:

- "graph instead of AI"

It is:

- "AI inside a controlled business flow"

That is a much stronger product story.

## 6. Why This Matters For Customer Demos Too

This point is often underestimated.

In demos, a free-form ReAct agent can look impressive for five minutes.
But a graph-backed business agent is usually more convincing over thirty minutes.

Why?

Because stakeholders quickly start asking questions like:

- How does it know which parcel is mine?
- What if I have several parcels?
- Can it act without asking me?
- Can it explain why it proposes rerouting?
- Does it always fetch operational context before acting?

A graph-backed answer is much stronger:

- yes, parcel resolution is a distinct business step
- yes, multiple parcels trigger a selection path
- no, rerouting is gated by an approval step
- yes, context collection is explicit before action

That makes the demo feel less like a toy and more like a real service.

## 7. A Useful Rule Of Thumb

Use `ReAct` when the business value comes mainly from:

- broad conversation
- open exploration
- tool opportunism
- flexible assistance

Use `Graph` when the business value comes mainly from:

- a clear service role
- a known customer journey
- explicit decision points
- protected actions
- stable, explainable orchestration

The parcel operations case clearly belongs to the second family.

## 8. What This Teaches For Fred v2

This example is important because it clarifies the intended split in the v2 runtime:

- `ReActAgentDefinition` is not the default answer to every agent problem
- `GraphAgentDefinition` is not just for drawing a pretty Mermaid diagram

The graph model exists because some agent roles are fundamentally workflow-shaped.

The parcel example proves that this is not an abstract architectural debate.
It is a product design decision with direct business consequences.

## 9. What This Also Teaches For Future SDK Work

This case is especially useful when thinking about long-term convergence with a `genai_sdk` style substrate.

It shows that a serious platform must support both:

- semantic intelligence
- explicit workflow control

If an SDK only makes it easy to build ReAct-style agents, it is not sufficient for business workflows like parcel operations.

For this family of agents, the platform must support:

- typed runtime context
- structured intent routing
- deterministic node sequencing
- explicit human approval
- structured UI outputs such as maps

That is why this demo matters beyond the demo itself.

It is a concrete test of whether Fred v2 can become a real business-agent platform rather than only a flexible tool-calling wrapper.

## 10. Bottom Line

For a parcel operations agent, the business promise is:

- understand my problem
- identify my parcel
- show me what is happening
- help me choose safely
- execute the right action only when appropriate

That promise is better served by a graph than by pure ReAct.

Not because graphs are more technical.
Because they are more faithful to the business journey the agent is supposed to embody.
