# Model Selection and Routing in Agentic AI Systems

## Overview

Modern AI applications increasingly rely on **multiple language models** rather than a single model. Different models offer different trade-offs in:

* reasoning capability
* latency
* cost
* reliability
* compliance constraints

As AI systems evolve into **multi-step agent pipelines**, the problem of **which model should be used for which task** becomes critical.

This problem is commonly referred to as **LLM routing** or **model selection**.

Without a structured approach, systems quickly become difficult to maintain:

* model choices become hardcoded in application code
* teams duplicate configuration logic
* switching providers becomes complex
* operational governance becomes impossible

For production systems — especially in **enterprise or critical environments** — a clear architecture for model selection is therefore required.

Several approaches exist in the ecosystem today. This document introduces the main ones and their trade-offs.

---

# The Model Selection Problem

In an agent-based AI system, a single user request may involve multiple reasoning steps.

Example pipeline:

```
User question
   ↓
Intent routing
   ↓
Planning
   ↓
Information retrieval
   ↓
Analysis
   ↓
Draft generation
   ↓
Self-check / correction
   ↓
Final answer
```

Not all of these steps require the same model.

For example:

| Phase            | Typical requirement |
| ---------------- | ------------------- |
| routing          | fast, cheap model   |
| planning         | strong reasoning    |
| draft generation | high quality        |
| self-check       | cheap verification  |

Using a single frontier model for everything is usually **inefficient and expensive**.

The system therefore needs a way to decide:

> Which model should be used for each step of the reasoning pipeline?

This is the **model routing problem**.

---

# Main Approaches to Model Selection

There are currently **four main approaches** used in AI systems.

---

# 1. Hard-Coded Model Selection

## Description

The simplest approach is to **choose models directly in code**.

Example:

```python
if task == "summarization":
    model = gpt4
elif task == "classification":
    model = gpt35
```

Or:

```python
llm = ChatOpenAI(model="gpt-4")
```

## Characteristics

* model selection is embedded in application code
* decisions are made by developers
* configuration is scattered across the codebase

## Advantages

* simple to implement
* minimal infrastructure

## Limitations

* difficult to maintain
* hard to change models globally
* duplicated logic across services
* poor governance

This approach is common in **early prototypes**, but rarely scales well.

---

# 2. Query Complexity Routing

## Description

In this approach, the system analyzes the **user query itself** to determine which model to use.

Typical idea:

```
simple query → cheap model
complex query → powerful model
```

The router may use:

* embeddings
* classifiers
* learned scoring models
* heuristics

Example:

```
if query_complexity < threshold:
    use small model
else:
    use frontier model
```

## Characteristics

* routing decisions are **automatic**
* the router analyzes prompts or queries
* often based on machine learning models

## Advantages

* can reduce costs automatically
* adapts to query complexity

## Limitations

* routing decisions are hard to explain
* unpredictable behavior
* difficult to validate in regulated environments
* limited understanding of multi-step agent workflows

This approach is popular in **AI gateways and research systems**.

---

# 3. Mixture-of-Experts Style Routing

## Description

Inspired by machine learning architectures, this approach routes requests to specialized models.

Example architecture:

```
            Router
               │
     ┌─────────┼─────────┐
     │         │         │
 math model  code model  chat model
```

The router decides which "expert" model should handle the request.

This idea originates from **Mixture-of-Experts (MoE)** architectures used in modern LLMs.

## Characteristics

* different models specialize in specific domains
* routing may be rule-based or learned
* common in experimental multi-agent systems

## Advantages

* good specialization
* flexible architecture

## Limitations

* still requires routing logic
* complex to maintain
* does not solve governance or configuration challenges

In practice, MoE ideas are more commonly used **inside models** than in application architecture.

---

# 4. Policy-Based Model Routing

## Description

Policy-based routing separates **model selection decisions from application code**.

Instead of embedding choices in code, the system defines **model profiles and routing rules**.

Example policy:

```
operation: routing          → fast model
operation: planning         → strong reasoning model
operation: draft_generation → high quality model
operation: self_check       → fast verification model
```

The agent pipeline declares **its reasoning phase**, and the routing policy selects the appropriate model.

Example configuration:

```
operation: planning
target_model: gpt-5
```

## Characteristics

* routing logic defined in configuration
* deterministic and auditable
* models organized into reusable profiles
* policies can evolve independently of agents

## Advantages

* strong governance
* easy to change models globally
* consistent conventions across teams
* suitable for regulated or critical environments

## Limitations

* requires clear conventions
* requires policy management infrastructure

This approach is increasingly used in **enterprise GenAI platforms**.

---

# Why Model Routing Matters for Agent Systems

Agent-based AI systems perform **multiple reasoning phases**.

Without structured routing:

* expensive models may be used unnecessarily
* model usage becomes inconsistent
* operational governance becomes difficult
* debugging model behavior becomes harder

A well-designed routing architecture enables:

* cost control
* deterministic behavior
* easier experimentation
* centralized governance

These properties are particularly important for **enterprise and critical systems**.

---

# Conclusion

Model routing is a fundamental architectural component of modern AI systems.

Four main approaches exist today:

| Approach                   | Key Idea                                    |
| -------------------------- | ------------------------------------------- |
| Hard-coded selection       | Models chosen directly in code              |
| Query complexity routing   | Router analyzes the prompt                  |
| Mixture-of-experts routing | Router selects specialized models           |
| Policy-based routing       | Centralized rules determine model selection |

Each approach has different trade-offs.

For **enterprise-grade AI platforms**, deterministic and policy-driven architectures are often preferred because they provide:

* operational control
* governance
* reproducibility
* predictable system behavior

The next section of this documentation will present **Fred's proposed model routing architecture**.
