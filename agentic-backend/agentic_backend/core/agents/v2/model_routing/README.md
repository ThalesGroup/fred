# V2 Model Routing Pattern (Isolated Slice)

This folder provides an isolated, `genai_sdk`-style pattern for centralized
chat-model routing in Fred v2.

Why isolated:
- avoid destabilizing current agent behavior
- make precedence semantics explicit and testable
- let teams review provider/resolver contracts before runtime wiring

## Core pieces

- `contracts.py`
  - policy contracts (`ModelRoutingPolicy`, `ModelRouteRule`, `ModelProfile`)
  - request/result contracts (`ModelSelectionRequest`, `ModelSelection`)
- `resolver.py`
  - deterministic precedence engine
- `provider.py`
  - provider abstraction (`ModelProvider`)
  - runtime adapter (`RoutedChatModelFactory`)
- `defaults.py`
  - generic default policy bootstrap from current `AIConfig`
    (`default_chat_model`, `default_language_model`)
- `catalog.py`
  - strict YAML loader for `models_catalog.yaml`
  - supports `common_model_settings` + per-capability defaults +
    profile-level overrides

## Precedence

Rules are resolved in this order:
1. highest specificity (`match` fields count)
2. first declared rule order in policy

If no rule matches, `default_profile_by_capability[capability]` is used.

## Example policy

```python
from fred_core import ModelConfiguration
from agentic_backend.core.agents.v2.model_routing import (
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
)

policy = ModelRoutingPolicy(
    default_profile_by_capability={ModelCapability.CHAT: "baseline"},
    profiles=(
        ModelProfile(
            profile_id="baseline",
            capability=ModelCapability.CHAT,
            model=ModelConfiguration(provider="openai", name="gpt-5.1", settings={"temperature": 0.0}),
        ),
        ModelProfile(
            profile_id="fast",
            capability=ModelCapability.CHAT,
            model=ModelConfiguration(provider="openai", name="gpt-5-mini", settings={"temperature": 0.0}),
        ),
    ),
    rules=(
        ModelRouteRule(
            rule_id="team-demo-default",
            capability=ModelCapability.CHAT,
            target_profile_id="fast",
            match=ModelRouteMatch(team_id="team-demo", purpose="chat"),
        ),
    ),
)
```

## Relation with your initial key/value idea

Your key/value examples:
- `default_chat_model`
- `default_chat_model_team_xxx`
- `default_chat_model_team_xxx_rico`

map directly to structured rules in this module, with strict validation and
explicit precedence.

## Agent-layer presets (example)

```python
from agentic_backend.agents.v2.production.basic_react.model_routing_presets import (
    build_default_policy_with_basic_react_presets,
)

policy = build_default_policy_with_basic_react_presets(ai_config=cfg.ai)
```

Default behavior:
- LogGenius uses `ai.default_language_model` (fallback `ai.default_chat_model`)
- RAG Expert uses `ai.default_chat_model`

Both can be overridden with explicit `ModelConfiguration` arguments.

## Runtime trial (now)

Catalog-first activation in `AgentFactory`:

- if `./config/models_catalog.yaml` exists (or path from
  `FRED_MODELS_CATALOG_FILE` / `FRED_V2_MODELS_CATALOG_FILE`), that file is loaded and used as routing
  policy source of truth.
- if the catalog file exists but is invalid, startup fails fast (no silent
  fallback).
- one catalog can mix providers (for example OpenAI + Azure APIM + Ollama/Mistral)
  in distinct profiles/rules.

Config-loader integration:
- the same catalog also seeds `ai.default_chat_model` and
  `ai.default_language_model` at startup.
- deployment can override capability defaults without editing the catalog:
  - `FRED_MODELS_DEFAULT_CHAT_PROFILE_ID`
  - `FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID`

Fallback activation:

- `FRED_V2_MODEL_ROUTING_PRESETS_ENABLED=1`

Behavior when enabled:
- v2 `ReActAgentDefinition` and v2 `GraphAgentDefinition` instances use
  `RoutedChatModelFactory`
- if no rule matches, the capability default is used (no regression path)

Settings merge order inside catalog:
1. `common_model_settings`
2. `common_model_settings_by_capability[capability]` (if present)
3. `profile.model.settings`

Verification:
- look for logs with prefix `[V2][MODEL_ROUTING]`
- `source=rule` confirms rule-based override (e.g. LogGenius, RAG Expert)

## Team + Agent demo rule shape

From a product perspective ("in team settings, pick another model for one agent"),
the backend mapping is:

- team default: one rule with `match.team_id`
- team+agent override: one rule with `match.team_id + match.agent_id`

Example:

```yaml
rules:
  - rule_id: chat-mistral-team-la-poste-default
    capability: chat
    target_profile_id: chat.ollama.mistral
    match:
      purpose: chat
      team_id: la-poste

  - rule_id: chat-custodian-la-poste-override
    capability: chat
    target_profile_id: chat.azure_apim.gpt4o
    match:
      purpose: chat
      team_id: la-poste
      agent_id: internal.react_profile.custodian
```

Expected behavior:
- any chat agent in `la-poste` uses Mistral by default;
- `internal.react_profile.custodian` in `la-poste` uses Azure APIM instead
  (more specific rule wins).

## YAML-only scope (current phase)

Current implementation scope is intentionally backend-only with one source of truth:

- `models_catalog.yaml` (or catalog path from env)
- no dedicated model-routing REST endpoints
- no runtime write path from UI

This keeps routing behavior deterministic and easy to validate before introducing
database-backed overrides and API contracts.

## ReAct phase routing behavior

v2 ReAct runtime now infers one operation per model call:

- `routing`: call happens after a user message (tool planning / intent routing)
- `planning`: call happens after one or more tool results

This enables team-wide policies such as:

```yaml
rules:
  - rule_id: ui.chat.react_phase.team.la_poste.routing
    capability: chat
    target_profile_id: chat.ollama.mistral
    match:
      purpose: chat
      team_id: la-poste
      operation: routing

  - rule_id: ui.chat.react_phase.team.la_poste.planning
    capability: chat
    target_profile_id: default.chat.openai.prod
    match:
      purpose: chat
      team_id: la-poste
      operation: planning
```
