"""
Offline unit tests for fred_runtime.model_routing.

Covers:
- contracts.py  — Pydantic validators (match values, rule shape normalization,
                  policy reference integrity, capability alignment)
- resolver.py   — deterministic rule selection (default, single rule, specificity
                  tie-breaking, multi-criteria, one-of tuples)
- catalog.py    — settings deep-merge and YAML loading

No mocks, no network, no filesystem side effects beyond tmp_path.
"""

from __future__ import annotations

import pytest
import yaml

from fred_core.common import ModelConfiguration
from fred_runtime.model_routing.catalog import ModelCatalog, load_model_catalog
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
)
from fred_runtime.model_routing.resolver import ModelRoutingResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model(provider: str = "openai", name: str = "gpt-4o") -> ModelConfiguration:
    return ModelConfiguration(provider=provider, name=name)


def _profile(
    profile_id: str,
    capability: ModelCapability = ModelCapability.CHAT,
    provider: str = "openai",
    name: str = "gpt-4o",
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        capability=capability,
        model=_model(provider=provider, name=name),
    )


def _minimal_policy(
    *,
    profile_id: str = "default.chat",
    rules: tuple[ModelRouteRule, ...] = (),
) -> ModelRoutingPolicy:
    return ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: profile_id},
        profiles=(_profile(profile_id),),
        rules=rules,
    )


def _rule(
    rule_id: str,
    target: str,
    *,
    operation: str,
    team_id: str | None = None,
    agent_id: str | None = None,
    user_id: str | None = None,
    purpose: str | None = None,
) -> ModelRouteRule:
    return ModelRouteRule(
        rule_id=rule_id,
        capability=ModelCapability.CHAT,
        target_profile_id=target,
        operation=operation,
        team_id=team_id,
        agent_id=agent_id,
        user_id=user_id,
        purpose=purpose,
    )


def _request(
    *,
    purpose: str = "chat",
    operation: str | None = None,
    team_id: str | None = None,
    agent_id: str | None = None,
    user_id: str | None = None,
) -> ModelSelectionRequest:
    return ModelSelectionRequest(
        capability=ModelCapability.CHAT,
        purpose=purpose,
        operation=operation,
        team_id=team_id,
        agent_id=agent_id,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# contracts — ModelRouteMatch validation
# ---------------------------------------------------------------------------


class TestModelRouteMatchValidation:
    def test_all_none_is_valid(self) -> None:
        m = ModelRouteMatch()
        assert m.defined_criteria_count() == 0

    def test_single_string_criterion(self) -> None:
        m = ModelRouteMatch(operation="routing")
        assert m.operation == "routing"
        assert m.defined_criteria_count() == 1

    def test_tuple_criterion(self) -> None:
        m = ModelRouteMatch(team_id=("team-a", "team-b"))
        assert m.team_id == ("team-a", "team-b")

    def test_all_criteria_count(self) -> None:
        m = ModelRouteMatch(
            purpose="chat",
            agent_id="myagent",
            team_id="t1",
            user_id="u1",
            operation="routing",
        )
        assert m.defined_criteria_count() == 5

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(Exception, match="non-empty string"):
            ModelRouteMatch(operation="   ")

    def test_empty_tuple_rejected(self) -> None:
        with pytest.raises(Exception):
            ModelRouteMatch(team_id=())

    def test_tuple_with_blank_item_rejected(self) -> None:
        with pytest.raises(Exception, match="non-empty strings"):
            ModelRouteMatch(operation=("routing", "  "))


# ---------------------------------------------------------------------------
# contracts — ModelRouteRule shape normalization
# ---------------------------------------------------------------------------


class TestModelRouteRuleNormalization:
    def test_flat_format_accepted(self) -> None:
        rule = ModelRouteRule(
            rule_id="r1",
            capability=ModelCapability.CHAT,
            target_profile_id="p1",
            operation="routing",
            team_id="team-a",
        )
        assert rule.match.operation == "routing"
        assert rule.match.team_id == "team-a"

    def test_legacy_match_block_accepted(self) -> None:
        rule = ModelRouteRule(
            rule_id="r1",
            capability=ModelCapability.CHAT,
            target_profile_id="p1",
            match={"operation": "planning", "purpose": "chat"},
        )
        assert rule.match.operation == "planning"
        assert rule.match.purpose == "chat"

    def test_flat_format_requires_operation(self) -> None:
        with pytest.raises(Exception, match="requires 'operation'"):
            ModelRouteRule(
                rule_id="r1",
                capability=ModelCapability.CHAT,
                target_profile_id="p1",
                team_id="team-a",
            )

    def test_empty_match_rejected(self) -> None:
        with pytest.raises(Exception, match="no criteria"):
            ModelRouteRule(
                rule_id="r1",
                capability=ModelCapability.CHAT,
                target_profile_id="p1",
            )

    def test_conflicting_flat_and_match_block_rejected(self) -> None:
        with pytest.raises(Exception, match="conflicting values"):
            ModelRouteRule(
                rule_id="r1",
                capability=ModelCapability.CHAT,
                target_profile_id="p1",
                operation="routing",
                match={"operation": "planning"},
            )

    def test_consistent_flat_and_match_block_accepted(self) -> None:
        rule = ModelRouteRule(
            rule_id="r1",
            capability=ModelCapability.CHAT,
            target_profile_id="p1",
            operation="routing",
            match={"operation": "routing", "team_id": "team-a"},
        )
        assert rule.match.operation == "routing"
        assert rule.match.team_id == "team-a"


# ---------------------------------------------------------------------------
# contracts — ModelRoutingPolicy reference validation
# ---------------------------------------------------------------------------


class TestModelRoutingPolicyValidation:
    def test_valid_minimal_policy(self) -> None:
        policy = _minimal_policy()
        assert len(policy.profiles) == 1

    def test_duplicate_profile_ids_rejected(self) -> None:
        with pytest.raises(Exception, match="unique profile_id"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "p1"},
                profiles=(_profile("p1"), _profile("p1")),
            )

    def test_unknown_default_profile_rejected(self) -> None:
        with pytest.raises(Exception, match="unknown profile_id"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "missing"},
                profiles=(_profile("p1"),),
            )

    def test_default_profile_capability_mismatch_rejected(self) -> None:
        embed_profile = _profile("embed.model", capability=ModelCapability.EMBEDDING)
        with pytest.raises(Exception, match="capability"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "embed.model"},
                profiles=(embed_profile,),
            )

    def test_rule_targeting_unknown_profile_rejected(self) -> None:
        rule = _rule("r1", "ghost.profile", operation="routing")
        with pytest.raises(Exception, match="unknown profile_id"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
                profiles=(_profile("default.chat"),),
                rules=(rule,),
            )

    def test_rule_capability_mismatch_rejected(self) -> None:
        embed_profile = _profile("embed.model", capability=ModelCapability.EMBEDDING)
        with pytest.raises(Exception):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
                profiles=(_profile("default.chat"), embed_profile),
                rules=(
                    ModelRouteRule(
                        rule_id="r1",
                        capability=ModelCapability.CHAT,
                        target_profile_id="embed.model",
                        operation="routing",
                    ),
                ),
            )

    def test_duplicate_rule_ids_rejected(self) -> None:
        p_chat = _profile("default.chat")
        r1 = _rule("same-id", "default.chat", operation="routing")
        r2 = _rule("same-id", "default.chat", operation="planning")
        with pytest.raises(Exception, match="unique rule_id"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
                profiles=(p_chat,),
                rules=(r1, r2),
            )


# ---------------------------------------------------------------------------
# resolver — default fallback and rule matching
# ---------------------------------------------------------------------------


class TestModelRoutingResolver:
    def test_returns_default_when_no_rules(self) -> None:
        resolver = ModelRoutingResolver(_minimal_policy())
        result = resolver.resolve(_request())
        assert result.source == ModelSelectionSource.DEFAULT
        assert result.profile_id == "default.chat"
        assert result.rule_id is None
        assert result.matched_criteria == 0

    def test_raises_when_no_default_for_capability(self) -> None:
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.EMBEDDING: "embed.p"},
            profiles=(_profile("embed.p", capability=ModelCapability.EMBEDDING),),
        )
        resolver = ModelRoutingResolver(policy)
        with pytest.raises(ValueError, match="No default profile"):
            resolver.resolve(_request())

    def test_single_matching_rule_wins(self) -> None:
        specific = _profile("specific.chat")
        rule = _rule("r1", "specific.chat", operation="routing", team_id="team-a")
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            rules=(rule,),
        )
        result = ModelRoutingResolver(policy).resolve(
            _request(operation="routing", team_id="team-a")
        )
        assert result.source == ModelSelectionSource.RULE
        assert result.profile_id == "specific.chat"
        assert result.rule_id == "r1"
        assert result.matched_criteria == 2

    def test_non_matching_rule_falls_through_to_default(self) -> None:
        specific = _profile("specific.chat")
        rule = _rule("r1", "specific.chat", operation="routing", team_id="team-a")
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            rules=(rule,),
        )
        result = ModelRoutingResolver(policy).resolve(
            _request(operation="planning", team_id="team-a")
        )
        assert result.source == ModelSelectionSource.DEFAULT

    def test_capability_filter_prevents_wrong_rule(self) -> None:
        embed_profile = _profile("embed.p", capability=ModelCapability.EMBEDDING)
        policy = ModelRoutingPolicy(
            default_profile_by_capability={
                ModelCapability.CHAT: "default.chat",
                ModelCapability.EMBEDDING: "embed.p",
            },
            profiles=(_profile("default.chat"), embed_profile),
            rules=(
                ModelRouteRule(
                    rule_id="embed-rule",
                    capability=ModelCapability.EMBEDDING,
                    target_profile_id="embed.p",
                    operation="routing",
                ),
            ),
        )
        result = ModelRoutingResolver(policy).resolve(_request(operation="routing"))
        assert result.source == ModelSelectionSource.DEFAULT
        assert result.profile_id == "default.chat"

    def test_more_specific_rule_beats_less_specific(self) -> None:
        broad = _profile("broad.chat")
        narrow = _profile("narrow.chat")
        rule_broad = _rule("r-broad", "broad.chat", operation="routing")
        rule_narrow = _rule(
            "r-narrow", "narrow.chat", operation="routing", team_id="team-a"
        )
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), broad, narrow),
            rules=(rule_broad, rule_narrow),
        )
        result = ModelRoutingResolver(policy).resolve(
            _request(operation="routing", team_id="team-a")
        )
        assert result.profile_id == "narrow.chat"
        assert result.matched_criteria == 2

    def test_first_declared_wins_on_equal_specificity(self) -> None:
        first = _profile("first.chat")
        second = _profile("second.chat")
        r1 = _rule("r1", "first.chat", operation="routing", team_id="team-a")
        r2 = _rule("r2", "second.chat", operation="routing", team_id="team-a")
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), first, second),
            rules=(r1, r2),
        )
        result = ModelRoutingResolver(policy).resolve(
            _request(operation="routing", team_id="team-a")
        )
        assert result.profile_id == "first.chat"
        assert result.rule_id == "r1"

    def test_tuple_one_of_matches(self) -> None:
        specific = _profile("specific.chat")
        rule = ModelRouteRule(
            rule_id="r1",
            capability=ModelCapability.CHAT,
            target_profile_id="specific.chat",
            operation=("routing", "planning"),
            team_id="team-a",
        )
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            rules=(rule,),
        )
        resolver = ModelRoutingResolver(policy)
        for op in ("routing", "planning"):
            result = resolver.resolve(_request(operation=op, team_id="team-a"))
            assert result.source == ModelSelectionSource.RULE
            assert result.profile_id == "specific.chat"

    def test_tuple_one_of_does_not_match_other_value(self) -> None:
        specific = _profile("specific.chat")
        rule = ModelRouteRule(
            rule_id="r1",
            capability=ModelCapability.CHAT,
            target_profile_id="specific.chat",
            operation=("routing", "planning"),
            team_id="team-a",
        )
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            rules=(rule,),
        )
        result = ModelRoutingResolver(policy).resolve(
            _request(operation="json_validation_fc", team_id="team-a")
        )
        assert result.source == ModelSelectionSource.DEFAULT

    def test_policy_property_exposed(self) -> None:
        policy = _minimal_policy()
        resolver = ModelRoutingResolver(policy)
        assert resolver.policy is policy


# ---------------------------------------------------------------------------
# catalog — deep merge and to_policy()
# ---------------------------------------------------------------------------


class TestModelCatalogToPolicy:
    def _make_catalog(
        self,
        *,
        common: dict | None = None,
        by_capability: dict | None = None,
        profile_settings: dict | None = None,
    ) -> ModelCatalog:
        return ModelCatalog(
            default_profile_by_capability={ModelCapability.CHAT: "p1"},
            profiles=(
                ModelProfile(
                    profile_id="p1",
                    capability=ModelCapability.CHAT,
                    model=ModelConfiguration(
                        provider="openai",
                        name="gpt-4o",
                        settings=profile_settings or {},
                    ),
                ),
            ),
            common_model_settings=common or {},
            common_model_settings_by_capability=by_capability or {},
        )

    def test_no_common_settings_passthrough(self) -> None:
        catalog = self._make_catalog()
        policy = catalog.to_policy()
        assert policy.profiles[0].model.provider == "openai"
        assert policy.profiles[0].model.name == "gpt-4o"

    def test_common_settings_applied(self) -> None:
        catalog = self._make_catalog(common={"temperature": 0.3})
        policy = catalog.to_policy()
        assert policy.profiles[0].model.settings["temperature"] == 0.3

    def test_capability_settings_override_common(self) -> None:
        catalog = self._make_catalog(
            common={"temperature": 0.3},
            by_capability={ModelCapability.CHAT: {"temperature": 0.7}},
        )
        policy = catalog.to_policy()
        assert policy.profiles[0].model.settings["temperature"] == 0.7

    def test_profile_settings_override_capability(self) -> None:
        catalog = self._make_catalog(
            common={"temperature": 0.3},
            by_capability={ModelCapability.CHAT: {"temperature": 0.7}},
            profile_settings={"temperature": 1.0},
        )
        policy = catalog.to_policy()
        assert policy.profiles[0].model.settings["temperature"] == 1.0

    def test_nested_settings_deep_merged(self) -> None:
        catalog = self._make_catalog(
            common={"azure": {"api_version": "2024-01", "endpoint": "https://base"}},
            profile_settings={"azure": {"endpoint": "https://override"}},
        )
        policy = catalog.to_policy()
        settings = policy.profiles[0].model.settings
        assert settings["azure"]["api_version"] == "2024-01"
        assert settings["azure"]["endpoint"] == "https://override"

    def test_to_policy_returns_valid_routing_policy(self) -> None:
        catalog = self._make_catalog()
        policy = catalog.to_policy()
        assert isinstance(policy, ModelRoutingPolicy)
        assert policy.default_profile_by_capability[ModelCapability.CHAT] == "p1"


class TestLoadModelCatalog:
    def test_loads_valid_yaml(self, tmp_path) -> None:
        content = {
            "version": "v1",
            "default_profile_by_capability": {"chat": "p1"},
            "profiles": [
                {
                    "profile_id": "p1",
                    "capability": "chat",
                    "model": {"provider": "openai", "name": "gpt-4o"},
                }
            ],
        }
        path = tmp_path / "catalog.yaml"
        path.write_text(yaml.dump(content), encoding="utf-8")
        catalog = load_model_catalog(path)
        assert catalog.profiles[0].profile_id == "p1"

    def test_empty_file_raises(self, tmp_path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_model_catalog(path)

    def test_non_mapping_raises(self, tmp_path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            load_model_catalog(path)

    def test_rules_survive_yaml_round_trip(self, tmp_path) -> None:
        content = {
            "version": "v1",
            "default_profile_by_capability": {"chat": "default.chat"},
            "profiles": [
                {
                    "profile_id": "default.chat",
                    "capability": "chat",
                    "model": {"provider": "openai", "name": "gpt-4o"},
                },
                {
                    "profile_id": "fast.chat",
                    "capability": "chat",
                    "model": {"provider": "openai", "name": "gpt-4o-mini"},
                },
            ],
            "rules": [
                {
                    "rule_id": "r1",
                    "capability": "chat",
                    "target_profile_id": "fast.chat",
                    "operation": "routing",
                    "team_id": "team-a",
                }
            ],
        }
        path = tmp_path / "catalog.yaml"
        path.write_text(yaml.dump(content), encoding="utf-8")
        catalog = load_model_catalog(path)
        policy = catalog.to_policy()
        assert len(policy.rules) == 1
        assert policy.rules[0].rule_id == "r1"
        assert policy.rules[0].match.team_id == "team-a"
