# Fred V2 Doc Status Map

Status: working navigation aid

## Why this file exists

The v2 work now spans several documents.

Some of them describe decisions that are already stable enough to rely on.
Others are intentionally still "active thinking" documents and should be read
as such.

This file separates those two categories so the team can quickly see:

- what is robust enough to treat as the current model
- what still deserves review, challenge, or follow-up work

## 1. Stable Enough To Rely On

These documents describe the current v2 direction in a way that is stable
enough for day-to-day development.

- [AGENTS.md](/home/dimi/run/reference/fred/agentic-backend/docs/AGENTS.md)
  - contributor-facing entry point for the current Fred agent model
- [V2_FEATURE_MAP.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_FEATURE_MAP.md)
  - practical map of the implemented v2 feature surface and how to test it
- [V2_RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md)
  - stable explanation of why Fred runtime and LangChain middleware are complementary, with explicit pros/costs
- [LANGGRAPH_POSTGRES_SAVER_EVALUATION.md](/home/dimi/run/reference/fred/agentic-backend/docs/LANGGRAPH_POSTGRES_SAVER_EVALUATION.md)
  - current decision note: keep Fred's own saver for now
- [GRAPH_RUNTIME_MATURITY_AND_LANGGRAPH_USAGE.md](/home/dimi/run/reference/fred/agentic-backend/docs/GRAPH_RUNTIME_MATURITY_AND_LANGGRAPH_USAGE.md)
  - current assessment of how much LangGraph remains, how robust Fred graph runtime is, and the observability ownership trade-off
- [V2_GRAPH_DEBUG_PLAYBOOK.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_GRAPH_DEBUG_PLAYBOOK.md)
  - operator-facing guide to diagnose v2 graph agent behavior and latency with Langfuse + KPI phases

## 2. Stable Core, But Still Active Working Contract

These documents are already useful and important, but they should still be read
as active design/contract material rather than frozen truth.

- [AGENT_SPECIFICATION_V2.md](/home/dimi/run/reference/fred/agentic-backend/docs/AGENT_SPECIFICATION_V2.md)
  - normative target, partially implemented
- [V2_GRAPH_RUNTIME_CONTRACT.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_GRAPH_RUNTIME_CONTRACT.md)
  - active contract for graph responsibilities and state semantics
- [GENAI_SDK_SPEC.md](/home/dimi/run/reference/fred/agentic-backend/docs/GENAI_SDK_SPEC.md)
  - architectural reading of how Fred could align with a broader SDK substrate
- [V2_MODEL_PROVIDER_PRIMER.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_MODEL_PROVIDER_PRIMER.md)
  - short meeting-ready primer for model routing/provider pattern and profile-level tuning

## 3. Deliberately Exploratory / Needs Continued Review

These documents are valuable, but they should be read as challenge material,
assessment notes, or active follow-up topics.

- [GENAI_SDK_COMPATIBILITY_CHALLENGE.md](/home/dimi/run/reference/fred/agentic-backend/docs/GENAI_SDK_COMPATIBILITY_CHALLENGE.md)
  - challenge gates before any naive SDK convergence
- [V2_LEGACY_FEATURE_SCAN.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_LEGACY_FEATURE_SCAN.md)
  - scan of what legacy capabilities still deserve elevation in v2
- [GRAPH_VS_REACT_POSTAL_CASE.md](/home/dimi/run/reference/fred/agentic-backend/docs/GRAPH_VS_REACT_POSTAL_CASE.md)
  - business case note used to justify graph over ReAct for the postal workflow
- [HISTORY_VS_CHECKPOINTING.md](/home/dimi/run/reference/fred/agentic-backend/docs/HISTORY_VS_CHECKPOINTING.md)
  - exploratory note on why transcript history and runtime checkpointing remain separate, and why a future event-sourced model is the more interesting unification path
- [AGENT_RUNTIME_LIFECYCLE_SPEC.md](/home/dimi/run/reference/fred/agentic-backend/docs/AGENT_RUNTIME_LIFECYCLE_SPEC.md)
  - still useful as historical/diagnostic context, but no longer the main target contract

## 4. How To Use This In Practice

If you want the current v2 story quickly, start here:

1. [AGENTS.md](/home/dimi/run/reference/fred/agentic-backend/docs/AGENTS.md)
2. [V2_FEATURE_MAP.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_FEATURE_MAP.md)
3. [V2_RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md)

If you are reviewing open design pressure, then continue with:

1. [AGENT_SPECIFICATION_V2.md](/home/dimi/run/reference/fred/agentic-backend/docs/AGENT_SPECIFICATION_V2.md)
2. [V2_GRAPH_RUNTIME_CONTRACT.md](/home/dimi/run/reference/fred/agentic-backend/docs/V2_GRAPH_RUNTIME_CONTRACT.md)
3. [GENAI_SDK_COMPATIBILITY_CHALLENGE.md](/home/dimi/run/reference/fred/agentic-backend/docs/GENAI_SDK_COMPATIBILITY_CHALLENGE.md)

## 5. Rule Of Thumb

If a document describes:

- the current runtime behavior
- the current feature surface
- or an explicit implementation decision already taken

then it belongs in "stable enough to rely on".

If a document mainly describes:

- open questions
- challenge gates
- follow-up feature families
- or a contract still being stress-tested by new agents

then it belongs in "needs continued review".
