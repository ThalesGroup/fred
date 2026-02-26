# Design Note — Tool Selection, Governance, and HITL in Fred

## Context & Problem Statement

In Fred, many agents are **equipped with tools** (local tools, MCP tools, long-running jobs via Temporal, etc.).

A recurring and **structural problem** appears in all such agents:

> **Given a user request, how does the agent decide which tool to suggest or call?**

In practice, this problem is often solved:
- ad-hoc,
- differently in every agent,
- using brittle heuristics (string parsing, regex, keywords),
- or by embedding implicit logic inside prompts.

This leads to:
- duplicated logic,
- non-deterministic behavior,
- poor auditability,
- difficulty enforcing governance (HITL, permissions, cost control),
- and inconsistent UX across agents.

This document explains **why this problem cannot be delegated entirely to LangChain/LangGraph**, what exists today, and **why Fred introduces a dedicated, shared design pattern**.

---

## What We Want (Target Properties)

A production-grade solution must satisfy **all** of the following:

1. **Standardized tool decision logic**  
   No agent-specific “intent router” code.

2. **Structured, deterministic outputs**  
   No parsing of free-text LLM responses.

3. **Explicit governance**  
   HITL, permissions, cost thresholds, and destructive actions must be enforced *outside* the LLM.

4. **Compatibility with long-running jobs**  
   (Temporal, async tasks, resume later).

5. **Reusability across agents**  
   Same mechanism for filesystem agents, corpus agents, admin agents, etc.

6. **Auditability**  
   Clear separation between:
   - what the model *suggested*
   - what the system *allowed*
   - what was *actually executed*

---

## What Exists in LangChain / LangGraph (and Why It Is Not Enough)

### 1. LangChain Tool Calling (Function Calling)

**What it provides**
- The LLM selects a tool and arguments in a structured way.
- No text parsing.

**Limitations**
- No concept of governance or policy.
- No HITL logic.
- No cost/risk awareness.
- No notion of “suggest vs execute”.
- No long-running task semantics.

➡️ **This solves tool *selection*, not platform *decision making*.**

---

### 2. LangGraph ToolNode

**What it provides**
- Automatic execution of a selected tool inside a graph.

**Limitations**
- Executes immediately.
- No approval gate.
- No policy enforcement.
- No async job tracking.

➡️ Suitable for simple agents, **not for a governed platform**.

---

### 3. HumanInTheLoopMiddleware (LangChain)

**What it provides**
- Intercepts certain tool calls and asks for human approval.

**Limitations**
- HITL rules are static and tool-specific.
- Does not decide *which* tool to call.
- Not designed for custom LangGraph orchestration.
- Not designed for Temporal / async workflows.

➡️ Useful as a *mechanism*, not as an architecture.

---

### 4. Classic LangChain Agents (ReAct loop)

**Why we explicitly do NOT use them**
- Implicit heuristics.
- Hard to reason about.
- Difficult to audit.
- Poor fit for long-running tasks.
- Difficult to enforce safety and cost constraints.

➡️ **Rejected by design** for Fred.

---

## Key Insight

> **There is no standard middleware in LangChain or LangGraph that solves
> “Which tool should I use?” + “Am I allowed to run it?” + “Should I ask a human first?”**

LangChain provides **primitives**.  
LangGraph provides **orchestration**.  
**Neither provides platform-level governance.**

This gap is intentional and out of scope for those libraries.

---

## The Correct Architectural Decomposition

Fred must explicitly separate concerns into **three layers**, reused by all agents:

### 1. Tool Planner (Decision Layer)

**Responsibility**
- Analyze the conversation and available tools.
- Propose **one of**:
  - Call a specific tool with arguments.
  - Ask for clarification.
  - Answer without using tools.

**Characteristics**
- Uses the LLM.
- Output is **structured** (Pydantic / JSON schema / function calling).
- Produces a *proposal*, not an execution.

**Critically**:  
➡️ The planner **does not execute anything**.

---

### 2. Tool Policy (Governance Layer)

**Responsibility**
- Decide whether the proposed action is allowed.

**Examples**
- Corpus-wide operations → HITL required.
- Destructive tools → HITL required.
- Expensive jobs → HITL required.
- User lacks permission → reject.
- Scope too broad → ask clarification.

**Characteristics**
- Deterministic.
- No LLM.
- Fully auditable.
- Configurable at platform level.

---

### 3. Tool Executor (Execution Layer)

**Responsibility**
- Execute the approved action.
- Handle:
  - local tools,
  - MCP tools,
  - Temporal jobs.

**Characteristics**
- No decision logic.
- No interpretation.
- Pure execution + logging + metrics.

---

## How HITL Fits Cleanly

HITL is **not** a special case.

It is simply a **policy outcome**:

- Planner → proposes tool call
- Policy → decides “requires approval”
- System → raises `interrupt(...)`
- User response → resumes execution or cancels

This avoids:
- embedding HITL logic in agents,
- duplicating confirmation prompts,
- inconsistent behavior across tools.

---

## Why This Must Be Centralized (and Not Per Agent)

If each agent:
- parses user text,
- decides tools differently,
- implements its own HITL logic,

then:
- behavior diverges over time,
- security reviews become impossible,
- adding a new tool requires touching many agents,
- UX becomes inconsistent.

**Centralization is mandatory** for a platform.

---

## Role of LangGraph in This Design

LangGraph is used to:
- orchestrate the flow,
- persist state,
- manage interrupts and resumes.

A **shared sub-graph** can be introduced:

