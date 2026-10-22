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

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import httpx
import pytest
import yaml
from conftest import ToolFriendlyFakeChatModel
from fred_runtime.app.agent_app import (
    _build_chat_model_factory,
    _catalog_for_advertisement,
    _project_model_catalog_response,
)
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.model_routing.catalog import (
    ModelCatalog,
    load_model_routing_policy_from_catalog,
)
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelNotUsableError,
    TeamRoutingProfileDriftError,
)
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentDefinition
from pydantic import ValidationError


def _catalog(**discovery: object) -> ModelCatalog:
    return ModelCatalog.model_validate(
        {
            "discovery": {
                "source_id": "gateway",
                "base_url": "https://models.example/v1",
                "default_model_id": "chat-a",
                **discovery,
            }
        }
    )


def _transport(payload: object, *, status: int = 200) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://models.example/v1/models"
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(respond)


def test_discovery_only_catalog_has_stable_routable_profiles(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = _catalog()
    first = catalog.resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}, {"id": "chat-b"}]})
    )
    reordered = catalog.resolve_discovery(
        transport=_transport({"data": [{"id": "chat-b"}, {"id": "chat-a"}]})
    )

    assert {p.profile_id for p in first.profiles} == {
        p.profile_id for p in reordered.profiles
    }
    assert {p.capability_id for p in first.profiles} == {
        p.capability_id for p in reordered.profiles
    }
    settings = first.to_policy().profiles[0].model.settings
    assert settings is not None
    assert settings["base_url"] == ("https://models.example/v1")
    default = first.default_profile_by_capability[ModelCapability.CHAT]
    assert next(p for p in first.profiles if p.profile_id == default).model.name == (
        "chat-a"
    )
    assert all(not p.supports_thinking for p in first.profiles)


def test_discovery_endpoint_overrides_common_openai_base(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = _catalog().model_copy(
        update={
            "common_model_settings": {"openai_api_base": "https://other.example/v1"}
        }
    )
    resolved = catalog.resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    settings = resolved.to_policy().profiles[0].model.settings
    assert settings is not None
    assert settings["base_url"] == "https://models.example/v1"
    assert "openai_api_base" not in settings


def test_optional_metadata_and_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    resolved = _catalog(include_model_ids=["chat-a"]).resolve_discovery(
        transport=_transport(
            {
                "data": [
                    {
                        "id": "chat-a",
                        "name": "Chat A",
                        "max_model_len": 32768,
                        "max_input_tokens": 30000,
                        "max_output_tokens": 2048,
                    },
                    {"id": "embedding-b"},
                ]
            }
        )
    )
    assert len(resolved.profiles) == 1
    assert resolved.profiles[0].model_display_name == "Chat A"
    assert resolved.profiles[0].context_window_tokens == 32768
    assert resolved.profiles[0].max_input_tokens == 30000
    assert resolved.profiles[0].max_output_tokens == 2048


def test_operator_display_name_overrides_gateway_name_without_changing_wire_id(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    resolved = _catalog(
        model_display_names={"chat-a": "  Team Chat  "}
    ).resolve_discovery(
        transport=_transport(
            {
                "data": [
                    {"id": "chat-a", "name": "Gateway A"},
                    {"id": "chat-b", "name": "Gateway B"},
                ]
            }
        )
    )

    first, second = resolved.profiles
    assert first.model.name == "chat-a"
    assert first.model_display_name == "Team Chat"
    assert second.model_display_name == "Gateway B"
    projected = _project_model_catalog_response(resolved)
    assert [(item.name, item.display_name) for item in projected.models] == [
        ("chat-a", "Team Chat"),
        ("chat-b", "Gateway B"),
    ]


def test_allowlist_ignores_invalid_or_duplicate_excluded_entries(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    resolved = _catalog(include_model_ids=["chat-a"]).resolve_discovery(
        transport=_transport(
            {
                "data": [
                    {"id": "chat-a"},
                    {"id": "embedding-b"},
                    {"id": "embedding-b"},
                    {"id": []},
                    {},
                ]
            }
        )
    )
    assert [profile.model.name for profile in resolved.profiles] == ["chat-a"]


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"other": []}, "no data list"),
        ({"data": []}, "no complete selected inventory"),
        ({"data": [{"id": "chat-a"}, {"id": "chat-a"}]}, "duplicate"),
        ({"data": [{"id": " "}]}, "invalid model id"),
        ({"data": [{"id": " chat-a"}]}, "invalid model id"),
        ({"data": [{"id": "x" * 257}]}, "invalid model id"),
        ({"data": [{"id": "chat-a\n"}]}, "invalid model id"),
        ({"data": [{"id": "chat-b"}]}, "missing its default model"),
    ],
)
def test_invalid_inventory_fails(monkeypatch, payload, message) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    with pytest.raises(ValueError, match=message):
        _catalog().resolve_discovery(transport=_transport(payload))


def test_http_failure_is_sanitized(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    with pytest.raises(ValueError, match="source 'gateway' failed: HTTP 503") as error:
        _catalog().resolve_discovery(transport=_transport({}, status=503))
    assert "test-secret" not in str(error.value)


def test_timeout_and_oversized_response_fail_without_leaking_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test-secret")

    with pytest.raises(ValueError, match="ReadTimeout") as timeout_error:
        _catalog().resolve_discovery(transport=httpx.MockTransport(timeout))
    assert "test-secret" not in str(timeout_error.value)

    oversized = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=b"x" * 1_048_577)
    )
    with pytest.raises(ValueError, match="exceeds 1 MiB"):
        _catalog().resolve_discovery(transport=oversized)


def test_static_catalog_never_fetches() -> None:
    catalog = ModelCatalog()
    assert catalog.resolve_discovery() is catalog


def test_pod_builder_advertises_its_routing_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(
        yaml.safe_dump(_catalog().model_dump(mode="json")), encoding="utf-8"
    )
    resolved = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    monkeypatch.setattr(ModelCatalog, "resolve_discovery", lambda self: resolved)
    config = AgentPodConfig.model_construct()
    config.set_models_catalog_path(str(path))

    factory = _build_chat_model_factory(config)
    assert isinstance(factory, RoutedChatModelFactory)
    snapshot = factory.catalog
    assert snapshot is resolved
    assert snapshot is not None
    assert _catalog_for_advertisement(str(path), snapshot) is resolved
    projected = _project_model_catalog_response(snapshot)
    assert [item.name for item in projected.models] == ["chat-a"]
    assert (
        projected.default_chat_profile_id
        == snapshot.default_profile_by_capability[ModelCapability.CHAT]
    )
    assert factory.with_provider(factory._provider).catalog is resolved


def test_policy_loader_resolves_a_discovery_catalog(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(
        yaml.safe_dump(_catalog().model_dump(mode="json")), encoding="utf-8"
    )
    resolved = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    monkeypatch.setattr(ModelCatalog, "resolve_discovery", lambda self: resolved)
    assert (
        load_model_routing_policy_from_catalog(path).profiles[0].model.name == "chat-a"
    )


def test_static_catalog_advertisement_still_reads_the_file(tmp_path) -> None:
    path = tmp_path / "models_catalog.yaml"
    path.write_text("version: v1\nprofiles: []\n", encoding="utf-8")
    assert _catalog_for_advertisement(str(path), None).profiles == ()
    path.write_text(
        "version: v1\nprofiles: []\ncommon_model_settings: {temperature: 0.5}\n",
        encoding="utf-8",
    )
    assert _catalog_for_advertisement(str(path), None).common_model_settings == {
        "temperature": 0.5
    }


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///tmp/models",
        "https://user@models.example/v1",
        "https://models.example/v1?q=x",
        "https://models.example/v1\n",
    ],
)
def test_discovery_url_rejects_non_endpoint_forms(base_url) -> None:
    with pytest.raises(ValidationError):
        _catalog(base_url=base_url)


def test_discovery_default_conflicts_with_static_default() -> None:
    with pytest.raises(ValidationError, match="conflicts"):
        ModelCatalog.model_validate(
            {
                "discovery": {
                    "source_id": "gateway",
                    "base_url": "https://models.example/v1",
                    "default_model_id": "chat-a",
                },
                "default_profile_by_capability": {"chat": "static"},
            }
        )


def test_discovery_config_rejects_invalid_model_ids() -> None:
    with pytest.raises(ValidationError, match="default_model_id"):
        _catalog(default_model_id=" chat-a")
    with pytest.raises(ValidationError, match="include_model_ids"):
        _catalog(include_model_ids=["chat-a", "chat-a"])


def test_discovery_config_rejects_invalid_display_name_mappings() -> None:
    with pytest.raises(ValidationError, match="model_display_names"):
        _catalog(model_display_names={" chat-a": "Chat"})
    with pytest.raises(ValidationError, match="model_display_names"):
        _catalog(model_display_names={"chat-a": "  "})
    with pytest.raises(ValidationError, match="model_display_names"):
        _catalog(model_display_names={"chat-a": "Chat\nA"})
    with pytest.raises(ValidationError, match="model_display_names"):
        _catalog(include_model_ids=["chat-a"], model_display_names={"chat-b": "Chat B"})


def test_discovered_model_uses_existing_grant_and_drift_gates(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    profile = catalog.profiles[0]

    class Provider:
        def build_model(self, model_config, *, capability):
            return ToolFriendlyFakeChatModel(responses=[])

    def binding(usable_ids, selected_profile=None):
        return BoundRuntimeContext(
            runtime_context=RuntimeContext(
                team_id="team-a",
                user_id="user-a",
                chat_default_profile_id=selected_profile,
            ),
            portable_context=PortableContext(
                request_id="request-a",
                correlation_id="request-a",
                actor="user-a",
                tenant="default",
                environment=PortableEnvironment.DEV,
                team_id="team-a",
                user_id="user-a",
            ),
            usable_model_ids=usable_ids,
        )

    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(catalog.to_policy()), provider=Provider()
    )
    definition = cast(AgentDefinition, SimpleNamespace(agent_id="agent-a"))
    with pytest.raises(ModelNotUsableError):
        factory.build_for_chat(definition=definition, binding=binding(()))
    model, selection = factory.build_for_chat(
        definition=definition, binding=binding((profile.capability_id,))
    )
    assert model is not None
    assert selection.profile_id == profile.profile_id
    with pytest.raises(TeamRoutingProfileDriftError):
        factory.build_for_chat(
            definition=definition,
            binding=binding(
                (profile.capability_id,),
                selected_profile="discovered.chat.gateway.removed",
            ),
        )
