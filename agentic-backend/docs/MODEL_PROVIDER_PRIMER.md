# Model Provider Primer (Quick Sync)

Status: practical onboarding note for model routing in Fred v2

## 1. What problem this solves

Before this pattern, model choice was mostly a global default (`ai.default_chat_model`)
plus ad-hoc per-agent tuning.

That does not scale for:

- profile-specific choices (`log_genius` vs `rag_expert`)
- team/user overrides
- future operation-level routing (`intent_router` vs `analysis`)

## 2. What we implemented (genai_sdk-style shape)

We introduced an isolated routing slice:

- `core/agents/v2/model_routing/contracts.py`
  - policy contract (`ModelRoutingPolicy`, `ModelProfile`, `ModelRouteRule`)
- `core/agents/v2/model_routing/resolver.py`
  - deterministic selection engine (`ModelRoutingResolver`)
- `core/agents/v2/model_routing/provider.py`
  - provider abstraction (`ModelProvider`) + Fred adapter (`FredCoreModelProvider`)
- `core/agents/v2/model_routing/defaults.py`
  - bootstrap from current `AIConfig` (no YAML redesign required)

This is aligned with genai_sdk principles:

- explicit contracts
- provider abstraction
- resolver/policy separation
- deterministic precedence and auditability

## 3. Runtime scope today

- Routed model selection is currently enabled for **v2 ReAct** when:
  - `FRED_V2_MODEL_ROUTING_PRESETS_ENABLED=1`
- Presets live in:
  - `agents/v2/production/basic_react/model_routing_presets.py`
- Graph runtime is not yet switched to routed factory by default.
- The abstraction is already compatible with future Graph integration because
  Graph and ReAct both consume `RuntimeServices.chat_model_factory`.

## 4. Fast mental model

1. Build policy (profiles + rules + defaults).
2. Resolver picks the winning profile for one request context.
3. Provider turns selected `ModelConfiguration` into a concrete model client.

## 5. Concrete code samples

### 5.1 Tune one profile now (LogGenius or RAG) without YAML migration

```python
from fred_core.common import ModelConfiguration

from agentic_backend.agents.v2.production.basic_react.model_routing_presets import (
    build_default_policy_with_basic_react_presets,
)

policy = build_default_policy_with_basic_react_presets(
    ai_config=self._configuration.ai,
    log_genius_chat_model=ModelConfiguration(
        provider="openai",
        name="gpt-5-mini",
        settings={"temperature": 0.0},
    ),
    rag_expert_chat_model=ModelConfiguration(
        provider="openai",
        name="gpt-5.1",
        settings={"temperature": 0.0},
    ),
)
```

This keeps defaults intact while giving explicit profile routing for:

- `internal.react_profile.log_genius`
- `rag.expert.v2` / `internal.react_profile.rag_expert`

### 5.2 Add team/user override rule (same mechanism, deterministic precedence)

```python
from agentic_backend.core.agents.v2.model_routing import (
    ModelCapability,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
)

extra_rule = ModelRouteRule(
    rule_id="override.rag.team_data.rico",
    capability=ModelCapability.CHAT,
    target_profile_id="preset.chat.rag_expert",
    match=ModelRouteMatch(
        purpose="chat",
        agent_id=("rag.expert.v2", "internal.react_profile.rag_expert"),
        team_id="team-data",
        user_id="rico",
    ),
)

policy = ModelRoutingPolicy(
    default_profile_by_capability=dict(base_policy.default_profile_by_capability),
    profiles=base_policy.profiles,
    rules=(*base_policy.rules, extra_rule),
)
```

Resolver precedence is:

1. most specific match
2. first rule order

### 5.3 Why this is ready for Graph agents too

Graph nodes already carry operation semantics:

```python
response = await context.invoke_model(
    [HumanMessage(content=prompt)],
    operation="analysis",
)
```

So later we can route by operation (`intent_router`, `analysis`, etc.) using the
same policy contract (`ModelSelectionRequest.operation`) instead of hard-coding
model switches inside each graph agent.

## 6. What to tell a non-v2 (Graph) teammate

- You do not need to migrate business logic first.
- The first value is centralizing model decisions outside agent code.
- ReAct is the first runtime wired by toggle; Graph can adopt the same pattern
  incrementally via `chat_model_factory`.
- The architecture goal is one shared policy/resolver/provider approach, not two
  separate tuning systems.

## 7. Current files to open during the demo

- `docs/MODEL_ROUTING_PATTERN.md`
- `core/agents/v2/model_routing/provider.py`
- `core/agents/v2/model_routing/contracts.py`
- `agents/v2/production/basic_react/model_routing_presets.py`
- `core/agents/agent_factory.py` (`_build_routed_chat_model_factory`)
- `agents/v2/candidate/aegis_graph_skeleton/agent.py` (Aegis-like v2 graph scaffold)

## 8. Concrete bridge example: v1 Aegis

Your teammate can map this pattern quickly from existing Aegis code:

- Aegis is currently v1 (`AgentFlow`): `agents/aegis/aegis_rag_expert.py`
- model is currently one global default:
  - `self.model = get_default_chat_model()` in `async_init(...)`
- multiple phases reuse the same model:
  - grading (`_grade_documents`)
  - draft generation (`_generate_draft`)
  - self-check (`_self_check`)
  - corrective planning (`_corrective_plan`)

That is exactly where centralized routing helps: phase-specific model choice
without scattering model config logic in each node.

### 8.1 Minimal migration shape (still v1 agent)

```python
# sketch for aegis_rag_expert.py (v1), using existing routing contracts
from typing import cast

from langchain_core.language_models.chat_models import BaseChatModel

from agentic_backend.application_context import get_configuration
from agentic_backend.core.agents.v2.model_routing import (
    build_default_policy_from_ai_config,
    ModelCapability,
    ModelSelectionRequest,
    ModelRoutingResolver,
    FredCoreModelProvider,
)

# one-time setup (e.g. async_init)
self._provider = FredCoreModelProvider()
self._resolver = ModelRoutingResolver(
    build_default_policy_from_ai_config(ai_config=get_configuration().ai)
)

def _model_for_phase(self, phase: str) -> BaseChatModel:
    request = ModelSelectionRequest(
        capability=ModelCapability.CHAT,
        purpose="chat",
        agent_id=self.get_id(),  # "Aegis"
        team_id=self.agent_settings.team_id,
        user_id=None,
        operation=phase,  # e.g. "generate_draft", "self_check"
    )
    selection = self._resolver.resolve(request)
    model_obj = self._provider.build_model(
        selection.model,
        capability=ModelCapability.CHAT,
    )
    return cast(BaseChatModel, model_obj)
```

Then in each phase:

- `_generate_draft`: `model = self._model_for_phase("generate_draft")`
- `_self_check`: `model = self._model_for_phase("self_check")`
- `_grade_documents`: `model = self._model_for_phase("grade_documents")`

### 8.2 Why this is useful for Aegis specifically

- heavy synthesis step can keep stronger model
- structured critic/grade steps can use smaller/faster model
- no change to graph topology or retrieval logic
- deterministic rules make decisions auditable (`rule_id`, `source`)

### 8.3 Recommended rollout

1. Start with one rule for `operation="self_check"` only.
2. Validate quality + latency.
3. Extend to `grade_documents` and `gap_queries`.
4. Keep `generate_draft` on the current stronger baseline until confidence is high.
