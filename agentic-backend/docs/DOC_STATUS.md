# Fred Docs Status Map

Status: working navigation aid (v2-first)

## Why this file exists

Fred documentation now mixes:

- current v2 runtime guidance (reference material)
- active contracts (still evolving)
- exploratory notes
- legacy v1 guides kept only for maintenance

This file gives a quick map so maintainers know what to trust first.

## 1. Stable Enough To Rely On

These docs describe the current runtime model and daily development workflow.

- [AGENTS.md](./AGENTS.md)
  - contributor-facing entry point for Fred agent authoring
- [FEATURE_MAP.md](./FEATURE_MAP.md)
  - practical map of implemented capabilities and retest paths
- [RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](./RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md)
  - stable architecture position on Fred runtime vs framework middleware
- [GRAPH_DEBUG_PLAYBOOK.md](./GRAPH_DEBUG_PLAYBOOK.md)
  - operator debugging playbook for graph and ReAct executions
- [MODEL_ROUTING_PATTERN.md](./MODEL_ROUTING_PATTERN.md)
  - model routing architecture (contracts, resolver, provider)
- [MODEL_ROUTING_USER_RULES_SPEC.md](./MODEL_ROUTING_USER_RULES_SPEC.md)
  - user-facing rule semantics for team/agent/operation routing
- [CATALOG_FILES_PATTERN.md](./CATALOG_FILES_PATTERN.md)
  - unified catalog-file strategy (`agents`, `mcp`, `models`)

## 2. Stable Core, Still Active Contract

These docs are important and already useful, but are still under active refinement.

- [AGENT_SPECIFICATION.md](./AGENT_SPECIFICATION.md)
  - normative runtime target contract
- [GRAPH_RUNTIME_CONTRACT.md](./GRAPH_RUNTIME_CONTRACT.md)
  - graph execution responsibilities and state semantics
- [MODEL_PROVIDER_PRIMER.md](./MODEL_PROVIDER_PRIMER.md)
  - compact onboarding note for model provider/routing discussions
- [GENAI_SDK_SPEC.md](./GENAI_SDK_SPEC.md)
  - architectural view of possible alignment with a broader SDK substrate

## 3. Exploratory / Review Material

These docs are valuable but should be read as challenge or follow-up material.

- [GENAI_SDK_COMPATIBILITY_CHALLENGE.md](./GENAI_SDK_COMPATIBILITY_CHALLENGE.md)
- [LEGACY_FEATURE_SCAN.md](./LEGACY_FEATURE_SCAN.md)
- [GRAPH_VS_REACT_POSTAL_CASE.md](./GRAPH_VS_REACT_POSTAL_CASE.md)
- [HISTORY_VS_CHECKPOINTING.md](./HISTORY_VS_CHECKPOINTING.md)
- [AGENT_RUNTIME_LIFECYCLE_SPEC.md](./AGENT_RUNTIME_LIFECYCLE_SPEC.md)

## 4. Legacy v1 Guides

Legacy docs are kept only for maintenance and migration context:

- [deprecated/v1/RAG_AGENT.md](./deprecated/v1/RAG_AGENT.md)
- [deprecated/v1/TABULAR_AGENT.md](./deprecated/v1/TABULAR_AGENT.md)

## 5. Recommended Reading Order

1. [AGENTS.md](./AGENTS.md)
2. [FEATURE_MAP.md](./FEATURE_MAP.md)
3. [RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md](./RUNTIME_VS_LANGCHAIN_MIDDLEWARE.md)
4. [MODEL_ROUTING_PATTERN.md](./MODEL_ROUTING_PATTERN.md)
