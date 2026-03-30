# Fred’s Approach to Model Selection

## Design Goal

Fred adopts a **policy-based model routing architecture** designed for **deterministic, auditable, and production-ready AI systems**.

The primary objective is to enable teams to build agent-based applications **without embedding model decisions in code**, while still allowing administrators and platform operators to enforce **clear governance rules**.

This approach is particularly important for environments where AI systems must remain:

* predictable
* secure
* cost-controlled
* maintainable across multiple teams and deployments

Rather than relying on automatic or opaque routing mechanisms, Fred favors **explicit policies and conventions**.

---

# Core Principles

Fred’s model selection architecture is guided by a few key principles.
# Fred Model Routing: A Pragmatic Overview

## The Goal

Fred introduces a **policy-based model routing system** that allows platform administrators to control which AI models are used during different phases of an agent workflow.

The objective is simple:

* keep **agents declarative**
* avoid **hardcoding model choices**
* allow **administrators to control model usage centrally**

Instead of embedding model choices inside agent code, Fred allows teams to define **routing policies** that automatically select the appropriate model profile.

---

# The Three Routing Dimensions

Fred separates model selection into three independent concepts.

| Dimension  | Meaning                      | Example                     |
| ---------- | ---------------------------- | --------------------------- |
| capability | technical interface required | chat, language              |
| purpose    | business intent of the agent | chatbot, rag, summarization |
| operation  | reasoning phase of the agent | routing, planning, analysis |

In practice, **operation is the primary routing mechanism**, while the other two help refine policies.

---

# Model Profiles

Fred introduces the concept of **model profiles**.

A profile is a reusable definition of a model configuration.

Example:

```yaml
profile_id: chat.openai.gpt5mini
capability: chat
model:
  provider: openai
  name: gpt-5-mini
```

Profiles allow administrators to control:

* which provider is used
* which model version is used
* operational parameters (timeouts, retries, etc.)

Agents never reference providers directly.
They rely on the routing system to select the correct profile.

---

# Routing by Agent Operation

Agent pipelines typically contain several reasoning phases.

Example:

```
User question
   ↓
intent_router
   ↓
planning
   ↓
analysis
   ↓
generate_draft
   ↓
self_check
   ↓
final answer
```

Different phases have different requirements.

| Operation      | Typical requirement |
| -------------- | ------------------- |
| intent_router  | very fast           |
| planning       | strong reasoning    |
| analysis       | strong reasoning    |
| generate_draft | high quality        |
| self_check     | fast verification   |

Fred allows administrators to define **rules mapping operations to model profiles**.

Example:

```yaml
rules:
  - rule_id: phase.routing.fast
    capability: chat
    operation: routing
    target_profile_id: chat.openai.gpt5mini

  - rule_id: phase.planning.quality
    capability: chat
    operation: planning
    target_profile_id: chat.openai.gpt5

  - rule_id: phase.generate_draft.quality
    capability: chat
    purpose: gap_analysis
    operation: generate_draft
    target_profile_id: chat.openai.gpt5

  - rule_id: phase.self_check.fast
    capability: chat
    purpose: gap_analysis
    operation: self_check
    target_profile_id: chat.openai.gpt5mini

  - rule_id: phase.corrective.fast
    capability: chat
    purpose: gap_analysis
    operation: corrective_queries
    target_profile_id: chat.openai.gpt5mini
```

In this configuration:

* routing uses a **fast inexpensive model**
* planning uses a **strong reasoning model**
* etc..

Agents automatically benefit from these policies without changing their code.

---

# Example: A Fred Team Administrator

Consider a Fred deployment where multiple teams run different agents.

A **team administrator** is responsible for managing model policies for their team.

For example, a team may operate several agents:

* a customer chatbot
* a document analysis assistant
* a RAG knowledge assistant

All of these agents share a common reasoning phase: **planning**.

If the administrator decides that planning quality must be improved, they can update the routing rule:

```yaml
- rule_id: team.phase.planning.high_quality
  capability: chat
  operation: planning
  target_profile_id: chat.openai.gpt52
```

After this change:

* every planning phase across all agents
* immediately uses the stronger model

No agent code needs to be modified.

---

# Example: Cost Optimization

A team administrator may also want to reduce infrastructure costs.

For example, they might decide that **self-check phases should always use a cheap model**.

```yaml
- rule_id: phase.self_check.fast
  capability: chat
  operation: self_check
  target_profile_id: chat.openai.gpt5mini
```

This ensures verification steps remain inexpensive while keeping high-quality models for reasoning tasks.

---

# Example: Domain-Specific Policies

Rules can optionally include **purpose** to specialize behavior for certain applications.

Example:

```yaml
- rule_id: rag.analysis.quality
  capability: chat
  purpose: rag
  operation: analysis
  target_profile_id: chat.openai.gpt52
```

In this case:

* RAG analysis steps use a stronger model
* other agents keep the default analysis model

This allows teams to fine-tune policies **without duplicating configurations**.

---

# Why This Approach Works Well

Fred's routing architecture provides several important benefits.

### Agents remain simple

Agents only declare what operation they are performing.
They never select models themselves.

---

### Model governance is centralized

Administrators control which models are used across the platform.

---

### Model upgrades become easy

Changing a model requires updating a **profile or rule**, not rewriting agents.

---

### Teams can evolve independently

Different teams can apply their own policies without impacting other agents.

---

# Summary

Fred treats model selection as a **platform responsibility** rather than an application concern.

By combining:

* reusable **model profiles**
* simple **operation-based routing**
* optional **purpose specialization**

Fred enables administrators to manage model usage across large agent ecosystems while keeping agent code clean and declarative.

### Separation of Concerns

Agents should focus on **reasoning and task execution**, not on selecting specific AI models.

Model selection is handled by a **separate policy layer** that interprets the agent’s intent and selects an appropriate model.

This keeps agent logic clean and prevents configuration from spreading throughout the codebase.

---

### Deterministic Behavior

Fred prioritizes **predictable and reproducible model selection**.

Given the same context and routing rules, the system should always select the same model.

This is essential for:

* debugging
* operational governance
* compliance and auditing

For this reason, Fred avoids routing strategies based on opaque machine learning classifiers or query heuristics.

---

### Convention-Based Agent Design

Agent pipelines typically follow a set of recurring reasoning phases, such as:

* routing
* planning
* analysis
* draft generation
* self-check

Fred encourages agents to **declare the operation they are performing**, using shared conventions.

Example:

```text
operation: planning
operation: routing
operation: self_check
```

This allows the model policy layer to apply routing rules consistently across different agents.

By using conventions, teams can introduce **new agents without rewriting configuration logic**.

---

### Model Profiles

Fred introduces the concept of **model profiles**.

A profile represents a reusable configuration that includes:

* the model provider
* the model name
* operational parameters (timeouts, retries, temperature, etc.)

Example concept:

```text
profile: chat.openai.gpt5mini
profile: chat.openai.gpt5
```

Agents never reference providers or model identifiers directly.
Instead, policies map operations to profiles.

This abstraction provides flexibility when models evolve or providers change.

---

### Centralized Routing Rules

Fred allows platform administrators to define **routing policies** that determine which model profile should be used for a given situation.

Rules can match conditions such as:

* capability (chat, language, etc.)
* agent purpose
* operation phase

Example concept:

```text
operation: planning → high-quality model
operation: routing → fast model
operation: self_check → low-cost model
```

These rules allow teams to balance:

* performance
* cost
* reasoning quality

without modifying agent code.

---

# Why Fred Uses Policy-Based Routing

Fred’s architecture is designed to support **large-scale enterprise AI systems** where multiple teams develop agents and applications.

Policy-based routing offers several advantages:

### Operational Governance

Model usage can be controlled centrally, making it easier to enforce cost limits, provider policies, or security constraints.

---

### Maintainability

Model choices can evolve without rewriting agents.

When new models appear or providers change, administrators can update policies rather than application code.

---

### Consistency Across Teams

Shared conventions and routing rules ensure that different agents behave consistently and follow the same architectural principles.

---

### Flexibility for Future Evolution

Because model selection is abstracted behind profiles and policies, Fred can support:

* multiple providers
* different deployment environments
* future routing strategies

without redesigning agent logic.

---

# Summary

Fred approaches model selection as a **platform responsibility rather than an application concern**.

Instead of embedding model choices in agent code, Fred introduces:

* reusable **model profiles**
* centralized **routing policies**
* shared **agent operation conventions**

Together, these elements form a **deterministic and governance-friendly model policy layer** that enables teams to build robust agent-based systems while maintaining control over model usage.

Future sections of this documentation will describe how these concepts are implemented in the Fred platform.
