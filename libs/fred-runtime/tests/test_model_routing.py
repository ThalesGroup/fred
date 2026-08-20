# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Offline unit tests for fred_runtime.model_routing.

Covers:
- contracts.py  — Pydantic policy reference integrity, capability alignment
- resolver.py   — deterministic selection (capability default,
                  agent_profile_overrides match/no-match, capability mismatch)
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
    ModelRoutingPolicy,
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
    agent_profile_overrides: dict[str, str] | None = None,
) -> ModelRoutingPolicy:
    return ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: profile_id},
        profiles=(_profile(profile_id),),
        agent_profile_overrides=agent_profile_overrides or {},
    )


def _request(
    *,
    agent_id: str | None = None,
) -> ModelSelectionRequest:
    return ModelSelectionRequest(
        capability=ModelCapability.CHAT,
        agent_id=agent_id,
    )


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

    def test_override_targeting_unknown_profile_rejected(self) -> None:
        with pytest.raises(Exception, match="unknown"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
                profiles=(_profile("default.chat"),),
                agent_profile_overrides={"rico": "ghost.profile"},
            )

    def test_override_with_empty_agent_id_key_rejected(self) -> None:
        with pytest.raises(Exception, match="non-empty agent ids"):
            ModelRoutingPolicy(
                default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
                profiles=(_profile("default.chat"),),
                agent_profile_overrides={"": "default.chat"},
            )


# ---------------------------------------------------------------------------
# resolver — capability default and agent_profile_overrides matching
# ---------------------------------------------------------------------------


class TestModelRoutingResolver:
    def test_returns_default_when_no_overrides(self) -> None:
        resolver = ModelRoutingResolver(_minimal_policy())
        result = resolver.resolve(_request())
        assert result.source == ModelSelectionSource.DEFAULT
        assert result.profile_id == "default.chat"

    def test_raises_when_no_default_for_capability(self) -> None:
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.EMBEDDING: "embed.p"},
            profiles=(_profile("embed.p", capability=ModelCapability.EMBEDDING),),
        )
        resolver = ModelRoutingResolver(policy)
        with pytest.raises(ValueError, match="No default profile"):
            resolver.resolve(_request())

    def test_matching_agent_override_wins(self) -> None:
        specific = _profile("specific.chat")
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            agent_profile_overrides={"rico": "specific.chat"},
        )
        result = ModelRoutingResolver(policy).resolve(_request(agent_id="rico"))
        assert result.source == ModelSelectionSource.AGENT_OVERRIDE
        assert result.profile_id == "specific.chat"

    def test_non_matching_agent_falls_through_to_default(self) -> None:
        specific = _profile("specific.chat")
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), specific),
            agent_profile_overrides={"rico": "specific.chat"},
        )
        result = ModelRoutingResolver(policy).resolve(_request(agent_id="other-agent"))
        assert result.source == ModelSelectionSource.DEFAULT

    def test_no_agent_id_on_request_falls_through_to_default(self) -> None:
        policy = ModelRoutingPolicy(
            default_profile_by_capability={ModelCapability.CHAT: "default.chat"},
            profiles=(_profile("default.chat"), _profile("specific.chat")),
            agent_profile_overrides={"rico": "specific.chat"},
        )
        result = ModelRoutingResolver(policy).resolve(_request(agent_id=None))
        assert result.source == ModelSelectionSource.DEFAULT

    def test_override_profile_capability_mismatch_falls_through_to_default(
        self,
    ) -> None:
        # The override maps to an EMBEDDING profile, but this request asks
        # for CHAT — the override must not apply across capabilities.
        embed_profile = _profile("embed.p", capability=ModelCapability.EMBEDDING)
        policy = ModelRoutingPolicy(
            default_profile_by_capability={
                ModelCapability.CHAT: "default.chat",
                ModelCapability.EMBEDDING: "embed.p",
            },
            profiles=(_profile("default.chat"), embed_profile),
            agent_profile_overrides={"rico": "embed.p"},
        )
        result = ModelRoutingResolver(policy).resolve(_request(agent_id="rico"))
        assert result.source == ModelSelectionSource.DEFAULT
        assert result.profile_id == "default.chat"

    def test_policy_property_exposed(self) -> None:
        policy = _minimal_policy()
        resolver = ModelRoutingResolver(policy)
        assert resolver.policy is policy

    def test_profile_or_none_returns_known_profile(self) -> None:
        resolver = ModelRoutingResolver(_minimal_policy())
        profile = resolver.profile_or_none("default.chat")
        assert profile is not None
        assert profile.profile_id == "default.chat"

    def test_profile_or_none_returns_none_for_unknown_id(self) -> None:
        resolver = ModelRoutingResolver(_minimal_policy())
        assert resolver.profile_or_none("ghost") is None


# ---------------------------------------------------------------------------
# NOTE (#2387): `TestResolveTeamOverride` lived here. The function it covered
# moved to `fred_sdk.contracts.context.resolve_effective_chat_profile` (one
# implementation, shared with control-plane), so its unit tests moved with it
# to `libs/fred-sdk/tests/test_context.py`. The provider-level wiring that
# feeds it stays covered by `tests/test_model_routing_provider.py`.
# ---------------------------------------------------------------------------

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
        settings = policy.profiles[0].model.settings
        assert settings is not None
        assert settings["temperature"] == 0.3

    def test_capability_settings_override_common(self) -> None:
        catalog = self._make_catalog(
            common={"temperature": 0.3},
            by_capability={ModelCapability.CHAT: {"temperature": 0.7}},
        )
        policy = catalog.to_policy()
        settings = policy.profiles[0].model.settings
        assert settings is not None
        assert settings["temperature"] == 0.7

    def test_profile_settings_override_capability(self) -> None:
        catalog = self._make_catalog(
            common={"temperature": 0.3},
            by_capability={ModelCapability.CHAT: {"temperature": 0.7}},
            profile_settings={"temperature": 1.0},
        )
        policy = catalog.to_policy()
        settings = policy.profiles[0].model.settings
        assert settings is not None
        assert settings["temperature"] == 1.0

    def test_nested_settings_deep_merged(self) -> None:
        catalog = self._make_catalog(
            common={"azure": {"api_version": "2024-01", "endpoint": "https://base"}},
            profile_settings={"azure": {"endpoint": "https://override"}},
        )
        policy = catalog.to_policy()
        settings = policy.profiles[0].model.settings
        assert settings is not None
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

    def test_agent_profile_overrides_survive_yaml_round_trip(self, tmp_path) -> None:
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
            "agent_profile_overrides": {"rico": "fast.chat"},
        }
        path = tmp_path / "catalog.yaml"
        path.write_text(yaml.dump(content), encoding="utf-8")
        catalog = load_model_catalog(path)
        policy = catalog.to_policy()
        assert policy.agent_profile_overrides == {"rico": "fast.chat"}
