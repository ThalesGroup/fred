from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.common import ModelConfiguration
from pydantic import ValidationError

from agentic_backend.agents.v2.production.basic_react.model_routing_presets import (
    BasicReActPresetProfileIds,
    BasicReActPresetRuleIds,
    build_default_policy_with_basic_react_presets,
)
from agentic_backend.common.structures import AIConfig
from agentic_backend.core.agents.v2.model_routing import (
    DefaultRoutingProfileIds,
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    ModelRoutingResolver,
    ModelSelectionRequest,
    ModelSelectionSource,
    build_default_policy_from_ai_config,
    load_model_routing_policy_from_catalog,
)


def _profile(
    profile_id: str,
    model_name: str,
    *,
    capability: ModelCapability = ModelCapability.CHAT,
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        capability=capability,
        model=ModelConfiguration(
            provider="openai",
            name=model_name,
            settings={"temperature": 0.0},
        ),
    )


def _ai_config(*, default_language_model: ModelConfiguration | None) -> AIConfig:
    payload = {
        "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1",
        "timeout": {"connect": 5, "read": 30},
        "default_chat_model": {
            "provider": "openai",
            "name": "gpt-5.1",
            "settings": {"temperature": 0.0},
        },
        "agents": [],
    }
    if default_language_model is not None:
        payload["default_language_model"] = default_language_model.model_dump(
            mode="json"
        )
    return AIConfig.model_validate(payload)


def test_model_routing_uses_default_profile_when_no_rule_matches() -> None:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "baseline"},
        profiles=(
            _profile("baseline", "gpt-5.1"),
            _profile("fast", "gpt-5-mini"),
        ),
        rules=(
            ModelRouteRule(
                rule_id="team-demo",
                capability=ModelCapability.CHAT,
                target_profile_id="fast",
                match=ModelRouteMatch(team_id="team-demo", purpose="chat"),
            ),
        ),
    )
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="basic.react.v2",
            team_id="other-team",
            user_id="user-1",
            operation=None,
        )
    )

    assert decision.source == ModelSelectionSource.DEFAULT
    assert decision.capability == ModelCapability.CHAT
    assert decision.profile_id == "baseline"
    assert decision.model.name == "gpt-5.1"
    assert decision.rule_id is None
    assert decision.matched_criteria == 0


def test_model_routing_prefers_more_specific_rule() -> None:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "baseline"},
        profiles=(
            _profile("baseline", "gpt-5.1"),
            _profile("team_default", "gpt-5-mini"),
            _profile("user_override", "gpt-5-nano"),
        ),
        rules=(
            ModelRouteRule(
                rule_id="team-default",
                capability=ModelCapability.CHAT,
                target_profile_id="team_default",
                match=ModelRouteMatch(team_id="team-a", purpose="chat"),
            ),
            ModelRouteRule(
                rule_id="team-user-override",
                capability=ModelCapability.CHAT,
                target_profile_id="user_override",
                match=ModelRouteMatch(team_id="team-a", user_id="rico", purpose="chat"),
            ),
        ),
    )
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="basic.react.v2",
            team_id="team-a",
            user_id="rico",
            operation=None,
        )
    )

    assert decision.source == ModelSelectionSource.RULE
    assert decision.rule_id == "team-user-override"
    assert decision.profile_id == "user_override"
    assert decision.model.name == "gpt-5-nano"
    assert decision.matched_criteria == 3


def test_model_routing_uses_first_declared_rule_when_specificity_is_equal() -> None:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "baseline"},
        profiles=(
            _profile("baseline", "gpt-5.1"),
            _profile("fast", "gpt-5-mini"),
            _profile("accurate", "gpt-5"),
        ),
        rules=(
            ModelRouteRule(
                rule_id="agent-fast",
                capability=ModelCapability.CHAT,
                target_profile_id="fast",
                match=ModelRouteMatch(agent_id="basic.react.v2", purpose="chat"),
            ),
            ModelRouteRule(
                rule_id="agent-accurate",
                capability=ModelCapability.CHAT,
                target_profile_id="accurate",
                match=ModelRouteMatch(agent_id="basic.react.v2", purpose="chat"),
            ),
        ),
    )
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="basic.react.v2",
            team_id="team-a",
            user_id="user-1",
            operation=None,
        )
    )

    assert decision.source == ModelSelectionSource.RULE
    assert decision.rule_id == "agent-fast"
    assert decision.profile_id == "fast"
    assert decision.model.name == "gpt-5-mini"


def test_model_routing_supports_one_of_match_values() -> None:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "baseline"},
        profiles=(
            _profile("baseline", "gpt-5.1"),
            _profile("analysis", "gpt-5"),
        ),
        rules=(
            ModelRouteRule(
                rule_id="analysis-ops",
                capability=ModelCapability.CHAT,
                target_profile_id="analysis",
                match=ModelRouteMatch(
                    purpose="chat",
                    operation=("analysis", "intent_router"),
                ),
            ),
        ),
    )
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="bid.intake.graph.v2",
            team_id="team-bid",
            user_id="user-1",
            operation="analysis",
        )
    )

    assert decision.source == ModelSelectionSource.RULE
    assert decision.rule_id == "analysis-ops"
    assert decision.profile_id == "analysis"
    assert decision.model.name == "gpt-5"


def test_model_routing_policy_rejects_unknown_rule_profile_reference() -> None:
    with pytest.raises(ValueError):
        ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "baseline"},
            profiles=(_profile("baseline", "gpt-5.1"),),
            rules=(
                ModelRouteRule(
                    rule_id="broken",
                    capability=ModelCapability.CHAT,
                    target_profile_id="does-not-exist",
                    match=ModelRouteMatch(team_id="team-a"),
                ),
            ),
        )


def test_model_routing_rule_requires_at_least_one_match_criterion() -> None:
    with pytest.raises(ValueError):
        ModelRouteRule(
            rule_id="invalid-catch-all",
            capability=ModelCapability.CHAT,
            target_profile_id="baseline",
            match=ModelRouteMatch(),
        )


def test_model_routing_rule_rejects_legacy_priority_field() -> None:
    with pytest.raises(ValidationError):
        ModelRouteRule(
            rule_id="legacy-priority",
            capability=ModelCapability.CHAT,
            target_profile_id="baseline",
            match=ModelRouteMatch(team_id="team-a"),
            priority=100,
        )


def test_model_routing_flat_rule_requires_operation() -> None:
    with pytest.raises(
        ValueError, match="flat format requires 'operation' at rule root"
    ):
        ModelRouteRule(
            rule_id="missing-operation",
            capability=ModelCapability.CHAT,
            target_profile_id="baseline",
            purpose="chat",
        )


def test_model_routing_uses_capability_specific_default() -> None:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={
            ModelCapability.CHAT: "default-chat",
            ModelCapability.LANGUAGE: "default-language",
        },
        profiles=(
            _profile("default-chat", "gpt-5.1", capability=ModelCapability.CHAT),
            _profile(
                "default-language",
                "gpt-5-mini",
                capability=ModelCapability.LANGUAGE,
            ),
        ),
    )
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.LANGUAGE,
            purpose="analysis",
            agent_id="basic.react.v2",
            team_id="team-a",
            user_id="rico",
            operation=None,
        )
    )

    assert decision.source == ModelSelectionSource.DEFAULT
    assert decision.capability == ModelCapability.LANGUAGE
    assert decision.profile_id == "default-language"


def test_model_routing_rejects_capability_mismatch_between_rule_and_profile() -> None:
    with pytest.raises(ValueError):
        ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default-chat"},
            profiles=(
                _profile("default-chat", "gpt-5.1", capability=ModelCapability.CHAT),
                _profile(
                    "default-embedding",
                    "text-embedding-3-large",
                    capability=ModelCapability.EMBEDDING,
                ),
            ),
            rules=(
                ModelRouteRule(
                    rule_id="broken-capability",
                    capability=ModelCapability.CHAT,
                    target_profile_id="default-embedding",
                    match=ModelRouteMatch(team_id="team-a"),
                ),
            ),
        )


def test_default_policy_bootstrap_uses_ai_defaults_with_language_override() -> None:
    ai_config = _ai_config(
        default_language_model=ModelConfiguration(
            provider="openai",
            name="gpt-5-mini",
            settings={"temperature": 0.0},
        )
    )
    policy = build_default_policy_from_ai_config(
        ai_config=ai_config,
        profile_ids=DefaultRoutingProfileIds(
            chat="default.chat", language="default.language"
        ),
    )

    assert policy.default_profile_by_capability[ModelCapability.CHAT] == "default.chat"
    assert (
        policy.default_profile_by_capability[ModelCapability.LANGUAGE]
        == "default.language"
    )
    profiles = {p.profile_id: p for p in policy.profiles}
    assert profiles["default.chat"].model.name == "gpt-5.1"
    assert profiles["default.language"].model.name == "gpt-5-mini"


def test_default_policy_bootstrap_falls_back_to_chat_for_language_when_missing() -> (
    None
):
    ai_config = _ai_config(default_language_model=None)
    policy = build_default_policy_from_ai_config(ai_config=ai_config)
    profiles = {p.profile_id: p for p in policy.profiles}

    chat_profile = profiles["default.chat"]
    language_profile = profiles["default.language"]

    assert chat_profile.model.provider == "openai"
    assert chat_profile.model.name == "gpt-5.1"
    assert language_profile.model.provider == "openai"
    assert language_profile.model.name == "gpt-5.1"


def test_default_policy_with_basic_react_presets_routes_log_genius_and_rag() -> None:
    ai_config = _ai_config(
        default_language_model=ModelConfiguration(
            provider="openai",
            name="gpt-5-mini",
            settings={"temperature": 0.0},
        )
    )
    policy = build_default_policy_with_basic_react_presets(
        ai_config=ai_config,
        profile_ids=DefaultRoutingProfileIds(
            chat="default.chat", language="default.language"
        ),
        preset_profile_ids=BasicReActPresetProfileIds(
            log_genius_chat="preset.chat.log_genius",
            rag_expert_chat="preset.chat.rag_expert",
        ),
        preset_rule_ids=BasicReActPresetRuleIds(
            log_genius_chat="preset.log_genius.chat",
            rag_expert_chat="preset.rag_expert.chat",
        ),
    )
    resolver = ModelRoutingResolver(policy)

    log_genius_decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="internal.react_profile.log_genius",
            team_id="team-ops",
            user_id="admin",
            operation=None,
        )
    )
    rag_expert_decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="internal.react_profile.rag_expert",
            team_id="team-rag",
            user_id="alice",
            operation=None,
        )
    )

    assert log_genius_decision.source == ModelSelectionSource.RULE
    assert log_genius_decision.rule_id == "preset.log_genius.chat"
    assert log_genius_decision.profile_id == "preset.chat.log_genius"
    assert log_genius_decision.model.name == "gpt-5-mini"

    assert rag_expert_decision.source == ModelSelectionSource.RULE
    assert rag_expert_decision.rule_id == "preset.rag_expert.chat"
    assert rag_expert_decision.profile_id == "preset.chat.rag_expert"
    assert rag_expert_decision.model.name == "gpt-5.1"


def test_default_policy_with_basic_react_presets_fallbacks_for_log_genius() -> None:
    ai_config = _ai_config(default_language_model=None)
    policy = build_default_policy_with_basic_react_presets(ai_config=ai_config)
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="internal.react_profile.log_genius",
            team_id="team-ops",
            user_id="admin",
            operation=None,
        )
    )

    assert decision.source == ModelSelectionSource.RULE
    assert decision.model.name == "gpt-5.1"


def test_model_catalog_file_loads_and_routes_graph_operation(tmp_path) -> None:
    catalog_file = tmp_path / "models_catalog.yaml"
    catalog_file.write_text(
        """
version: v1
default_profile_by_capability:
  chat: default.chat
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
    operation: analysis
    agent_id: bid.intake.graph.v2
    target_profile_id: graph.analysis
        """.strip(),
        encoding="utf-8",
    )

    policy = load_model_routing_policy_from_catalog(catalog_file)
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="bid.intake.graph.v2",
            team_id="team-bid",
            user_id="alice",
            operation="analysis",
        )
    )
    assert decision.source == ModelSelectionSource.RULE
    assert decision.rule_id == "bid-intake-analysis"
    assert decision.profile_id == "graph.analysis"
    assert decision.model.name == "gpt-5"


def test_model_catalog_file_accepts_legacy_match_rule_shape(tmp_path) -> None:
    catalog_file = tmp_path / "models_catalog.yaml"
    catalog_file.write_text(
        """
version: v1
default_profile_by_capability:
  chat: default.chat
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
      agent_id: bid.intake.graph.v2
      operation: analysis
        """.strip(),
        encoding="utf-8",
    )

    policy = load_model_routing_policy_from_catalog(catalog_file)
    resolver = ModelRoutingResolver(policy)

    decision = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="bid.intake.graph.v2",
            team_id="team-bid",
            user_id="alice",
            operation="analysis",
        )
    )
    assert decision.source == ModelSelectionSource.RULE
    assert decision.rule_id == "bid-intake-analysis"
    assert decision.profile_id == "graph.analysis"
    assert decision.model.name == "gpt-5"


def test_model_catalog_file_rejects_empty_payload(tmp_path) -> None:
    catalog_file = tmp_path / "models_catalog.yaml"
    catalog_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        load_model_routing_policy_from_catalog(catalog_file)


def test_model_catalog_merges_common_settings_and_profile_overrides(tmp_path) -> None:
    catalog_file = tmp_path / "models_catalog.yaml"
    catalog_file.write_text(
        """
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
common_model_settings_by_capability:
  chat:
    stream: true
default_profile_by_capability:
  chat: default.chat
profiles:
  - profile_id: default.chat
    capability: chat
    model:
      provider: openai
      name: gpt-5-mini
      settings:
        temperature: 0.0
        timeout:
          read: 90.0
rules: []
        """.strip(),
        encoding="utf-8",
    )

    policy = load_model_routing_policy_from_catalog(catalog_file)
    profile = next(p for p in policy.profiles if p.profile_id == "default.chat")
    settings = profile.model.settings or {}

    assert settings["max_retries"] == 0
    assert settings["stream"] is True
    assert settings["temperature"] == 0.0
    assert settings["timeout"]["connect"] == 10.0
    assert settings["timeout"]["read"] == 90.0
    assert settings["timeout"]["write"] == 30.0
    assert settings["http_client_limits"]["max_connections"] == 500


def test_repo_models_catalog_bootstrap_has_no_team_rules_and_uses_defaults() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    candidates = (
        repo_root / "config" / "models_catalog.yaml",
        repo_root / "config.sav" / "models_catalog.yaml",
    )
    catalog_file = next((path for path in candidates if path.exists()), None)
    if catalog_file is None:
        pytest.skip("No repository models catalog found under config/ or config.sav/.")
    policy = load_model_routing_policy_from_catalog(catalog_file)
    resolver = ModelRoutingResolver(policy)

    # Derive expected default from the catalog rather than hardcoding it,
    # so this test stays green when the catalog's default profile changes.
    expected_default_chat_profile_id = policy.default_profile_by_capability[
        ModelCapability.CHAT
    ]
    expected_default_profile = next(
        p for p in policy.profiles if p.profile_id == expected_default_chat_profile_id
    )

    team_query = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="internal.react_profile.log_genius",
            team_id="la-poste",
            user_id="alice",
            operation=None,
        )
    )
    assert team_query.source == ModelSelectionSource.DEFAULT
    assert team_query.rule_id is None
    assert team_query.profile_id == expected_default_chat_profile_id
    assert team_query.model.provider == expected_default_profile.model.provider
    assert team_query.model.name == expected_default_profile.model.name

    another_team_query = resolver.resolve(
        ModelSelectionRequest(
            capability=ModelCapability.CHAT,
            purpose="chat",
            agent_id="internal.react_profile.custodian",
            team_id="team-platform",
            user_id="alice",
            operation=None,
        )
    )
    assert another_team_query.source == ModelSelectionSource.DEFAULT
    assert another_team_query.rule_id is None
    assert another_team_query.profile_id == expected_default_chat_profile_id
