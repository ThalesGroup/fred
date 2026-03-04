# Model Routing Pattern (GenAI SDK Style, Isolated)

## Why this exists

Fred currently relies on one global default chat model (`ai.default_chat_model`) and
many agents call `get_default_chat_model()` directly. That works for bootstrap, but it
does not scale for:

- team-specific model choices
- user-specific overrides
- operation/phase-specific choices (routing vs analysis vs summary)
- safe rollout without impacting all agents

This document describes an isolated pattern added under:

- `agentic_backend/core/agents/v2/model_routing/`

The slice is intentionally **not wired by default** into runtime creation.

User-facing rule examples are documented in:
- [MODEL_ROUTING_USER_RULES_SPEC.md](/home/dimi/run/reference/fred/agentic-backend/docs/MODEL_ROUTING_USER_RULES_SPEC.md)

For the broader cross-domain catalog strategy (`models`, `agents`, `mcp`),
see [`CATALOG_FILES_PATTERN.md`](/home/dimi/run/reference/fred/agentic-backend/docs/CATALOG_FILES_PATTERN.md).

## Design goals

1. Keep v2 runtime stable while introducing policy-driven model selection.
2. Use a `genai_sdk`-style contract + provider + resolver separation.
3. Make precedence deterministic and testable.
4. Avoid ad-hoc key naming and configuration drift.
5. Keep routing generic by capability (`chat`, `language`, `embedding`, `image`).

## Pattern pieces

- `contracts.py`
  - `ModelRoutingPolicy`: full policy contract
  - `ModelProfile`: named immutable model profile
  - `ModelRouteRule`: one matching rule
  - `ModelSelectionRequest` / `ModelSelection`: input/output contracts
- `resolver.py`
  - `ModelRoutingResolver`: deterministic rule evaluation
- `provider.py`
  - `ModelProvider` protocol (replaceable)
  - `FredCoreModelProvider` default implementation
  - `RoutedChatModelFactory` adapter compatible with v2 `ChatModelFactoryPort`
- `defaults.py`
  - `build_default_policy_from_ai_config(...)` bootstrap from existing
    `AIConfig` (`default_chat_model`, `default_language_model`)
- `catalog.py`
  - strict loader for external `models_catalog.yaml` (Pydantic-validated)

- `agents/v2/production/basic_react/model_routing_presets.py`
  - `build_default_policy_with_basic_react_presets(...)` concrete Basic ReAct
    presets for:
    - `internal.react_profile.log_genius` (lightweight by default)
    - `rag.expert.v2` and `internal.react_profile.rag_expert` (stronger by default)

## Precedence semantics

The resolver applies:

1. Highest rule specificity (number of criteria in `match`)
2. First rule order in policy

If nothing matches, capability-specific default is used via
`default_profile_by_capability`.

## Why this is better than dynamic key naming

An approach like:

- `default_chat_model`
- `default_chat_model_team_xxx`
- `default_chat_model_team_xxx_rico`

is intuitive but hard to validate and reason about at scale.

Structured policy contracts bring:

- explicit schema validation
- explicit precedence
- explicit audit metadata (`rule_id`, `source`)
- straightforward UI/API representation

## How to adopt safely

Phase 1 (current):
- Keep existing runtime behavior.
- Validate policy semantics with unit tests only.
- Bootstrap policy from current `AIConfig` so no YAML migration is required.
- Optional: use `build_default_policy_with_basic_react_presets(...)` to
  encode immediate product decisions (LogGenius vs RAG Expert) without touching
  runtime wiring.

Phase 2:
- Inject `RoutedChatModelFactory` only for selected v2 agents/environments.
- Track selection metadata in traces.

Current practical behavior:
- If `./config/models_catalog.yaml` exists (or path from
  `FRED_MODELS_CATALOG_FILE` / `FRED_V2_MODELS_CATALOG_FILE`), routed model selection is enabled and this
  catalog is the source of truth for model routing.
- If this catalog file exists but is invalid, startup fails fast (no silent
  fallback).
- The same catalog can contain multiple providers (OpenAI, Azure APIM/OpenAI,
  Ollama/Mistral) in one place.
- Deployment can switch capability defaults without editing the catalog:
  - `FRED_MODELS_DEFAULT_CHAT_PROFILE_ID`
  - `FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID`
- Otherwise, set `FRED_V2_MODEL_ROUTING_PRESETS_ENABLED=1` to enable legacy
  preset routing.
- Routed selection now applies to both v2 ReAct and v2 Graph runtimes
  (same `ChatModelFactoryPort` seam).
- Runtime emits `[V2][MODEL_ROUTING]` logs; `source=rule` means explicit rule
  match.

## `models_catalog.yaml` schema (v1)

```yaml
version: v1
common_model_settings:
  max_retries: 0
  timeout:
    connect: 10.0
    read: 120.0
    write: 30.0
    pool: 5.0
  http_client_limits:
    max_connections: 500
    max_keepalive_connections: 200
    keepalive_expiry_seconds: 10
default_profile_by_capability:
  chat: default.chat
  language: default.language
profiles:
  - profile_id: default.chat
    capability: chat
    model:
      provider: openai
      name: gpt-5-mini
      settings:
        temperature: 0.0
  - profile_id: graph.analysis
    capability: chat
    model:
      provider: openai
      name: gpt-5
      settings:
        temperature: 0.0
rules:
  - rule_id: bid-intake-analysis
    capability: chat
    target_profile_id: graph.analysis
    match:
      purpose: chat
      agent_id: bid.intake.graph.v2
      operation: analysis
```

Merge semantics:
- `common_model_settings` applies to all profiles.
- `common_model_settings_by_capability` (optional) applies next.
- `profile.model.settings` is applied last and overrides common defaults.

Phase 3:
- Extend request context with operation-level routing where needed.
- Add admin UI for policy CRUD with validation.
