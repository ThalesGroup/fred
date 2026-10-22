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

import asyncio
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
import yaml
from conftest import ToolFriendlyFakeChatModel
from fred_core import OrganizationPermission
from fred_runtime.app.agent_app import (
    _build_chat_model_factory,
    _catalog_for_advertisement,
    _model_catalog_refresh_permission,
    _ModelCatalogRefreshRequest,
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
    ModelBinding,
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


def test_refresh_permission_requires_platform_admin_for_new_endpoint() -> None:
    approved = "https://models.example/v1/models"
    assert (
        _model_catalog_refresh_permission(
            _ModelCatalogRefreshRequest(models_url=approved), approved
        )
        == OrganizationPermission.CAN_MANAGE_CAPABILITIES
    )
    assert (
        _model_catalog_refresh_permission(
            _ModelCatalogRefreshRequest(
                models_url="https://attacker.example/v1/models"
            ),
            approved,
        )
        == OrganizationPermission.CAN_MANAGE_PLATFORM
    )
    assert (
        _model_catalog_refresh_permission(
            _ModelCatalogRefreshRequest(models_url=approved), None
        )
        == OrganizationPermission.CAN_MANAGE_PLATFORM
    )


def _multi_source_catalog() -> ModelCatalog:
    return ModelCatalog.model_validate(
        {
            "discoveries": [
                {"source_id": "east", "base_url": "https://east.example/v1"},
                {"source_id": "west", "base_url": "https://west.example/v1"},
            ]
        }
    )


def test_multiple_sources_keep_distinct_model_identities(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "shared-chat"}]})

    catalog = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(respond)
    )
    assert len(catalog.profiles) == 2
    assert len({profile.profile_id for profile in catalog.profiles}) == 2
    assert len({profile.capability_id for profile in catalog.profiles}) == 2
    response = _project_model_catalog_response(catalog)
    assert {source.source_id for source in response.discovery_sources} == {
        "east",
        "west",
    }
    assert all(
        len(source.discovered_model_ids) == 1 for source in response.discovery_sources
    )


@pytest.mark.asyncio
async def test_refresh_one_source_preserves_other_source_inventory(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))

    def initial_response(request: httpx.Request) -> httpx.Response:
        model_id = "east-chat" if request.url.host == "east.example" else "west-chat"
        return httpx.Response(200, json={"data": [{"id": model_id}]})

    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(initial_response)
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    refreshed = await factory.refresh_catalog(
        str(path),
        source_id="east",
        models_url="https://new-east.example/v1/models",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": [{"id": "new-east-chat"}]}
            )
        ),
    )
    assert {profile.model.name for profile in refreshed.profiles} == {
        "new-east-chat",
        "west-chat",
    }
    east = refreshed.discovery_source("east")
    west = refreshed.discovery_source("west")
    assert east is not None and east.base_url == "https://new-east.example/v1"
    assert west is not None and west.base_url == "https://west.example/v1"


@pytest.mark.asyncio
async def test_source_revision_does_not_fence_another_source(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))
    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": [{"id": f"{request.url.host}-old"}]}
            )
        )
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    await factory.refresh_catalog(
        str(path),
        source_id="west",
        models_url="https://new-west.example/v1/models",
        revision=5,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "west-new"}]})
        ),
    )
    await factory.refresh_catalog(
        str(path),
        source_id="west",
        models_url="https://new-west.example/v1/models",
        revision=6,
    )
    await factory.refresh_catalog(
        str(path),
        source_id="west",
        models_url="https://stale-west.example/v1/models",
        revision=5,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "stale-west"}]})
        ),
    )
    await factory.refresh_catalog(
        str(path),
        source_id="east",
        models_url="https://new-east.example/v1/models",
        revision=1,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "east-new"}]})
        ),
    )
    assert factory.active_revision_for("east") == 1
    assert factory.active_revision_for("west") == 6
    active = factory.catalog
    assert active is not None
    assert {profile.model.name for profile in active.profiles} == {
        "east-new",
        "west-new",
    }


@pytest.mark.asyncio
async def test_rollback_one_source_preserves_other_source_update(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))
    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": [{"id": f"{request.url.host}-old"}]}
            )
        )
    )
    candidate = initial.resolve_discovery(
        source_id="east",
        models_url="https://new-east.example/v1/models",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "east-new"}]})
        ),
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    factory._prepared["east-token"] = (
        ModelRoutingResolver(candidate.to_policy()),
        candidate,
        "east",
    )
    await factory.activate_prepared_catalog("east-token", revision=1)
    await factory.refresh_catalog(
        str(path),
        source_id="west",
        models_url="https://new-west.example/v1/models",
        revision=5,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "west-new"}]})
        ),
    )
    rolled_back = await factory.rollback_prepared_catalog("east-token")
    assert {profile.model.name for profile in rolled_back.profiles} == {
        "east.example-old",
        "west-new",
    }
    assert factory.active_revision_for("east") == 0
    assert factory.active_revision_for("west") == 5


@pytest.mark.asyncio
async def test_delegated_token_cannot_restore_a_replaced_source_url(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))
    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-a"}]})
        )
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    old_candidate = initial.resolve_discovery(
        source_id="east",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-new"}]})
        ),
    )
    factory._prepared["old-token"] = (
        ModelRoutingResolver(old_candidate.to_policy()),
        old_candidate,
        "east",
    )
    await factory.refresh_catalog(
        str(path),
        source_id="east",
        models_url="https://new-east.example/v1/models",
        revision=1,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-b"}]})
        ),
    )
    with pytest.raises(ValueError, match="changes the active discovery URL"):
        await factory.activate_prepared_catalog(
            "old-token", revision=2, allow_url_change=False
        )
    assert factory.active_revision_for("east") == 1
    assert factory.catalog is not None
    active_east = factory.catalog.discovery_source("east")
    assert active_east is not None
    assert active_east.base_url == "https://new-east.example/v1"

    factory._prepared["new-token"] = (
        ModelRoutingResolver(old_candidate.to_policy()),
        old_candidate,
        "east",
    )
    await factory.activate_prepared_catalog("new-token", revision=2)
    with pytest.raises(ValueError, match="changes the active discovery URL"):
        await factory.rollback_prepared_catalog("new-token", allow_url_change=False)
    assert factory.active_revision_for("east") == 2


@pytest.mark.asyncio
async def test_delegated_direct_refresh_cannot_publish_after_url_change(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))
    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-a"}]})
        )
    )
    old_candidate = initial.resolve_discovery(
        source_id="east",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-old"}]})
        ),
    )
    new_candidate = initial.resolve_discovery(
        source_id="east",
        models_url="https://new-east.example/v1/models",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-new"}]})
        ),
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_discovery(*args, models_url: str, **kwargs) -> ModelCatalog:
        if models_url == "https://new-east.example/v1/models":
            return new_candidate
        started.set()
        await release.wait()
        return old_candidate

    monkeypatch.setattr(ModelCatalog, "resolve_discovery_async", delayed_discovery)
    refresh = asyncio.create_task(
        factory.refresh_catalog(
            str(path),
            source_id="east",
            models_url="https://east.example/v1/models",
            force=True,
            allow_url_change=False,
        )
    )
    await started.wait()
    await factory.refresh_catalog(
        str(path),
        source_id="east",
        models_url="https://new-east.example/v1/models",
        revision=1,
        force=True,
    )
    release.set()
    with pytest.raises(ValueError, match="changed during refresh"):
        await refresh
    assert factory.catalog is not None
    active_east = factory.catalog.discovery_source("east")
    assert active_east is not None
    assert active_east.base_url == "https://new-east.example/v1"


@pytest.mark.asyncio
async def test_failed_source_backoffs_are_independent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_multi_source_catalog().model_dump(mode="json")))
    initial = _multi_source_catalog().resolve_discovery(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": [{"id": f"{request.url.host}-old"}]}
            )
        )
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    requests: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    for source_id in ("east", "west"):
        with pytest.raises(ValueError, match="HTTP 503"):
            await factory.refresh_catalog(
                str(path),
                source_id=source_id,
                models_url=f"https://new-{source_id}.example/v1/models",
                transport=httpx.MockTransport(fail),
            )
    for source_id in ("east", "west"):
        await factory.refresh_catalog(
            str(path),
            source_id=source_id,
            models_url=f"https://new-{source_id}.example/v1/models",
            transport=httpx.MockTransport(fail),
        )
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_model_detail_is_fetched_only_for_a_discovered_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, json={"id": "chat-a", "max_context_length": 131072})

    detail = await catalog.fetch_discovered_model_detail(
        source_id="gateway",
        model_id="chat-a",
        transport=httpx.MockTransport(respond),
    )
    assert detail["max_context_length"] == 131072
    assert requests == ["https://models.example/v1/models/chat-a"]
    with pytest.raises(ValueError, match="Unknown discovered model"):
        await catalog.fetch_discovered_model_detail(
            source_id="gateway",
            model_id="not-listed",
            transport=httpx.MockTransport(respond),
        )
    assert len(requests) == 1


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


def test_catalog_projection_uses_resolved_discovery_provenance(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = ModelCatalog.model_validate(
        {
            "discovery": {
                "source_id": "gateway",
                "base_url": "https://models.example/v1",
            },
            "profiles": [
                {
                    "profile_id": "discovered.chat.gateway.pinned",
                    "capability": "chat",
                    "model": {"provider": "openai", "name": "pinned"},
                }
            ],
        }
    )
    resolved = catalog.resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )

    assert len(resolved.discovered_profile_ids) == 1
    assert resolved.discovered_profile_ids[0] != "discovered.chat.gateway.pinned"
    assert _project_model_catalog_response(resolved).discovered_model_ids == [
        resolved.profiles[1].capability_id
    ]


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


def test_static_profiles_remain_routable_when_discovered_inventory_changes(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    catalog = ModelCatalog.model_validate(
        {
            "default_profile_by_capability": {"chat": "chat.static"},
            "profiles": [
                {
                    "profile_id": "chat.static",
                    "capability": "chat",
                    "model": {"provider": "openai", "name": "static-chat"},
                }
            ],
            "discovery": {
                "source_id": "gateway",
                "base_url": "https://models.example/v1",
            },
        }
    )
    first = catalog.resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    later = catalog.resolve_discovery(
        transport=_transport({"data": []}), allow_missing_default=True
    )
    assert {profile.model.name for profile in first.profiles} == {
        "static-chat",
        "chat-a",
    }
    assert [profile.model.name for profile in later.profiles] == ["static-chat"]
    assert later.default_profile_by_capability[ModelCapability.CHAT] == "chat.static"


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


def test_chat_capability_filters_only_when_advertised(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    resolved = _catalog().resolve_discovery(
        transport=_transport(
            {
                "data": [
                    {
                        "id": "chat-a",
                        "capabilities": {"completion_chat": True},
                        "max_context_length": 131072,
                    },
                    {"id": "embedding-b", "capabilities": {"completion_chat": False}},
                    {"id": "unknown-c"},
                ]
            }
        )
    )
    assert [profile.model.name for profile in resolved.profiles] == [
        "chat-a",
        "unknown-c",
    ]
    assert resolved.profiles[0].context_window_tokens == 131072
    assert resolved.verified_chat_profile_ids == (resolved.profiles[0].profile_id,)


def test_refresh_accepts_confirmed_empty_inventory(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    resolved = _catalog().resolve_discovery(
        transport=_transport({"data": []}), allow_missing_default=True
    )
    assert resolved.profiles == ()
    assert resolved.default_profile_by_capability == {}
    assert resolved.to_policy().profiles == ()


@pytest.mark.asyncio
async def test_live_refresh_replaces_verified_catalog_and_keeps_it_on_failure(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_catalog().model_dump(mode="json")))
    initial = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    second = await factory.refresh_catalog(
        str(path),
        force=True,
        transport=_transport({"data": [{"id": "chat-b"}]}),
    )
    assert {profile.model.name for profile in second.profiles} == {"chat-b"}
    assert factory.catalog is second
    with pytest.raises(ValueError, match="HTTP 503"):
        await factory.refresh_catalog(
            str(path), force=True, transport=_transport({}, status=503)
        )
    assert factory.catalog is second


@pytest.mark.asyncio
async def test_concurrent_turns_share_one_discovery_refresh(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_catalog().model_dump(mode="json")))
    initial = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"data": [{"id": "chat-b"}]})

    results = await asyncio.gather(
        *(
            factory.refresh_catalog(
                str(path),
                models_url="https://other.example/v1/models",
                transport=httpx.MockTransport(respond),
            )
            for _ in range(20)
        )
    )
    assert calls == 1
    assert all(result is factory.catalog for result in results)


@pytest.mark.asyncio
async def test_cancelled_turn_does_not_cancel_shared_refresh(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_catalog().model_dump(mode="json")))
    initial = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json={"data": [{"id": "chat-b"}]})

    transport = httpx.MockTransport(respond)
    first = asyncio.create_task(
        factory.refresh_catalog(
            str(path),
            models_url="https://other.example/v1/models",
            revision=1,
            transport=transport,
        )
    )
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(
        factory.refresh_catalog(
            str(path),
            models_url="https://other.example/v1/models",
            revision=1,
            transport=transport,
        )
    )
    release.set()
    assert {profile.model.name for profile in (await second).profiles} == {"chat-b"}
    assert calls == 1


@pytest.mark.asyncio
async def test_older_turn_cannot_replace_newer_admin_catalog(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    path = tmp_path / "models_catalog.yaml"
    path.write_text(yaml.safe_dump(_catalog().model_dump(mode="json")))
    initial = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(initial.to_policy()), catalog=initial
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def old_response(request: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(200, json={"data": [{"id": "chat-old"}]})

    old = asyncio.create_task(
        factory.refresh_catalog(
            str(path),
            models_url="https://old.example/v1/models",
            revision=1,
            transport=httpx.MockTransport(old_response),
        )
    )
    await started.wait()
    newer = await factory.refresh_catalog(
        str(path),
        models_url="https://new.example/v1/models",
        revision=2,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "chat-new"}]})
        ),
    )
    release.set()
    assert await old is newer
    assert factory.catalog is newer
    assert {profile.model.name for profile in newer.profiles} == {"chat-new"}


def test_models_url_override_changes_inference_base(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://other.example/v1/models"
        return httpx.Response(200, json={"data": [{"id": "chat-a"}]})

    resolved = _catalog().resolve_discovery(
        models_url="https://other.example/v1/models",
        transport=httpx.MockTransport(respond),
    )
    assert resolved.profiles[0].model.settings == {
        "base_url": "https://other.example/v1"
    }


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
    monkeypatch.setattr(
        ModelCatalog, "resolve_discovery", lambda self, **kwargs: resolved
    )
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


def test_pod_can_boot_before_saved_discovery_url_is_applied(
    monkeypatch, tmp_path
) -> None:
    path = tmp_path / "models_catalog.yaml"
    path.write_text(
        yaml.safe_dump(_catalog().model_dump(mode="json")), encoding="utf-8"
    )
    monkeypatch.setattr(
        ModelCatalog,
        "resolve_discovery",
        lambda self, **kwargs: (_ for _ in ()).throw(ValueError("unavailable")),
    )
    config = AgentPodConfig.model_construct()
    config.set_models_catalog_path(str(path))
    factory = _build_chat_model_factory(config)
    assert isinstance(factory, RoutedChatModelFactory)
    assert factory.catalog is not None
    assert factory.catalog.discovery is not None
    assert factory.catalog.profiles == ()


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
        "https://models.example/v1?",
        "https://models.example/v1#",
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


def test_confirmed_removed_team_default_uses_separate_platform_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    before = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-a"}]})
    )
    after = _catalog().resolve_discovery(
        transport=_transport({"data": [{"id": "chat-b"}]}),
        allow_missing_default=True,
    )
    removed = before.profiles[0]

    class Provider:
        def build_model(self, model_config, *, capability):
            assert model_config.name == "chat-b"
            return ToolFriendlyFakeChatModel(responses=[])

    factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(after.to_policy()),
        provider=Provider(),
        catalog=after,
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            team_id="team-a",
            user_id="user-a",
            chat_default_profile_id=removed.profile_id,
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
        usable_model_ids=(removed.capability_id,),
        confirmed_removed_chat_profiles={removed.profile_id: removed.capability_id},
        platform_chat_model_fallback=ModelBinding.model_validate(
            {
                "provider": "openai",
                "name": "chat-b",
                "settings": {"base_url": "https://models.example/v1"},
            }
        ),
    )
    _, selection = factory.build_for_chat(
        definition=cast(AgentDefinition, SimpleNamespace(agent_id="agent-a")),
        binding=binding,
    )
    assert selection.source.value == "platform_fallback"
    assert selection.model.name == "chat-b"

    with pytest.raises(TeamRoutingProfileDriftError):
        factory.build_for_chat(
            definition=cast(AgentDefinition, SimpleNamespace(agent_id="agent-a")),
            binding=binding.model_copy(update={"confirmed_removed_chat_profiles": {}}),
        )

    no_team_choice = binding.model_copy(
        update={
            "runtime_context": binding.runtime_context.model_copy(
                update={"chat_default_profile_id": None}
            ),
            "usable_model_ids": (),
        }
    )
    with pytest.raises(ModelNotUsableError):
        factory.build_for_chat(
            definition=cast(AgentDefinition, SimpleNamespace(agent_id="agent-a")),
            binding=no_team_choice,
        )

    manual_catalog = ModelCatalog.model_validate(
        {
            "discovery": {
                "source_id": "gateway",
                "base_url": "https://models.example/v1",
            },
            "profiles": [
                {
                    "profile_id": "chat.manual",
                    "capability": "chat",
                    "model": {
                        "provider": "openai",
                        "name": "tested-chat",
                        "settings": {"base_url": "https://manual.example/v1"},
                    },
                }
            ],
        }
    ).resolve_discovery(transport=_transport({"data": [{"id": "chat-b"}]}))

    class ManualProvider:
        def build_model(self, model_config, *, capability):
            assert model_config.name == "tested-chat"
            assert model_config.settings["base_url"] == "https://manual.example/v1"
            return ToolFriendlyFakeChatModel(responses=[])

    manual_factory = RoutedChatModelFactory(
        resolver=ModelRoutingResolver(manual_catalog.to_policy()),
        provider=ManualProvider(),
        catalog=manual_catalog,
    )
    manual_binding = binding.model_copy(
        update={
            "platform_chat_model_fallback": None,
            "platform_chat_model_fallback_profile_id": "chat.manual",
        }
    )
    _, manual_selection = manual_factory.build_for_chat(
        definition=cast(AgentDefinition, SimpleNamespace(agent_id="agent-a")),
        binding=manual_binding,
    )
    assert manual_selection.source.value == "platform_fallback"
    assert manual_selection.profile_id == "chat.manual"
    with pytest.raises(ValueError, match="unavailable"):
        manual_factory.build_for_chat(
            definition=cast(AgentDefinition, SimpleNamespace(agent_id="agent-a")),
            binding=manual_binding.model_copy(
                update={"platform_chat_model_fallback_profile_id": "chat.missing"}
            ),
        )
