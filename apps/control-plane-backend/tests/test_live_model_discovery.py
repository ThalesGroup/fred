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

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from control_plane_backend.model_discovery import service
from control_plane_backend.model_discovery.service import validate_models_url
from control_plane_backend.model_discovery.store import (
    ModelDiscoveryStateStore,
    PlatformModelFallbackStore,
    StoredDiscoverySourceState,
)
from control_plane_backend.models.base import Base
from control_plane_backend.models.model_discovery_models import (
    ModelDiscoverySourceStateRow,
    PlatformModelFallbackRow,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fred_core import KeycloakUser, OrganizationPermission
from fred_sdk.contracts.context import ModelBinding
from sqlalchemy.ext.asyncio import create_async_engine


def _model(name: str) -> dict:
    return {
        "id": f"model__openai__{name}",
        "name": name,
        "provider": "openai",
        "chat_profile_ids": [f"discovered.chat.gateway.{name}"],
    }


@pytest.mark.asyncio
async def test_successful_inventory_diff_and_failure_preserve_confirmed_removals() -> (
    None
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        Base.metadata.tables[ModelDiscoverySourceStateRow.__tablename__]
                    ],
                )
            )
        store = ModelDiscoveryStateStore(engine)
        first = await store.save_success(
            source_id="gateway",
            yaml_url="https://models.example/v1/models",
            effective_url="https://models.example/v1/models",
            inventory=[_model("a"), _model("b")],
        )
        assert first is not None
        assert first.active_url == first.yaml_url
        assert first.new_ids == ["model__openai__a", "model__openai__b"]
        second = await store.save_success(
            source_id="gateway",
            yaml_url=first.yaml_url,
            effective_url=first.yaml_url,
            inventory=[_model("b"), _model("c")],
        )
        assert second is not None
        assert second.new_ids == ["model__openai__c"]
        assert [item["id"] for item in second.removed] == ["model__openai__a"]
        failed = await store.record_failure(
            source_id="gateway",
            yaml_url="https://new-models.example/v1/models",
            error="timeout",
        )
        assert failed.last_error == "timeout"
        assert failed.yaml_url == "https://new-models.example/v1/models"
        assert failed.removed == second.removed
        assert failed.inventory == second.inventory
        assert failed.active_url == second.active_url
        returned = await store.save_success(
            source_id="gateway",
            yaml_url=first.yaml_url,
            effective_url=first.yaml_url,
            inventory=[_model("a"), _model("b"), _model("c")],
        )
        assert returned is not None
        assert returned.new_ids == []
        assert returned.removed == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_url_override_and_fallback_persist_independently() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        Base.metadata.tables[
                            ModelDiscoverySourceStateRow.__tablename__
                        ],
                        Base.metadata.tables[PlatformModelFallbackRow.__tablename__],
                    ],
                )
            )
        states = ModelDiscoveryStateStore(engine)
        initial = await states.save_success(
            source_id="gateway",
            yaml_url="https://models.example/v1/models",
            effective_url="https://models.example/v1/models",
            inventory=[_model("a")],
        )
        assert initial is not None
        saved = await states.save_success(
            source_id="gateway",
            yaml_url="https://models.example/v1/models",
            effective_url="https://other.example/v1/models",
            inventory=[_model("b")],
            override_update=True,
            override_url="https://other.example/v1/models",
            expected_override_url=None,
            updated_by="admin",
        )
        assert saved is not None
        assert saved.effective_url == "https://other.example/v1/models"
        assert saved.active_url == saved.effective_url
        stale = await states.save_success(
            source_id="gateway",
            yaml_url="https://models.example/v1/models",
            effective_url="https://third.example/v1/models",
            inventory=[],
            override_update=True,
            override_url="https://third.example/v1/models",
            expected_override_url=None,
        )
        assert stale is None
        persisted = await ModelDiscoveryStateStore(engine).get("gateway")
        assert persisted is not None
        assert persisted.effective_url == saved.effective_url
        binding = ModelBinding.model_validate(
            {
                "provider": "openai",
                "name": "chat-b",
                "settings": {"base_url": "https://other.example/v1"},
            }
        )
        fallback = PlatformModelFallbackStore(engine)
        await fallback.set(binding, updated_by="admin")
        assert await PlatformModelFallbackStore(engine).get() == binding
        await fallback.set_profile_id("chat.manual", updated_by="admin")
        assert await fallback.get_profile_id() == "chat.manual"
        assert await fallback.get() is None
        await fallback.delete()
        assert await fallback.get() is None
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/models",
        "https://user@host/v1/models",
        "https://host/v1/models?x=1",
        "https://host/v1/other",
    ],
)
def test_discovery_override_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_models_url(url)


@pytest.mark.asyncio
async def test_url_override_requires_platform_admin_before_store_access() -> None:
    class Rebac:
        async def check_user_permission_or_raise(
            self,
            user: KeycloakUser,
            permission: OrganizationPermission,
            resource_id: str,
        ) -> None:
            assert permission == OrganizationPermission.CAN_MANAGE_PLATFORM
            raise PermissionError("delegated feature manager")

    deps = cast(
        ProductServiceDependencies,
        SimpleNamespace(team_dependencies=SimpleNamespace(rebac=Rebac())),
    )
    with pytest.raises(PermissionError, match="delegated feature manager"):
        await service.set_url(
            cast(KeycloakUser, object()),
            deps,
            source_id="gateway",
            url="https://attacker.example/v1/models",
            authorization=None,
        )


@pytest.mark.asyncio
async def test_unreachable_runtime_is_a_transient_warning(monkeypatch) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    async def no_names(*args, **kwargs) -> dict[str, str]:
        return {}

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    monkeypatch.setattr(service, "model_display_name_overrides", no_names)
    row = StoredDiscoverySourceState(
        source_id="gateway",
        yaml_url="https://models.example/v1/models",
        override_url=None,
        active_url="https://models.example/v1/models",
        revision=1,
        inventory=[_model("a")],
        removed=[],
        new_ids=[],
        last_success_at=None,
        last_attempt_at=None,
        last_error=None,
    )

    class Store:
        async def list_all(self) -> list[StoredDiscoverySourceState]:
            return [row]

        async def record_failure(self, **kwargs) -> None:
            pytest.fail("A pod outage must not be persisted as a source failure")

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "pod-b.example":
            raise httpx.ConnectError("unreachable")
        return httpx.Response(
            200,
            json={
                "models": [_model("a")],
                "discovery_sources": [
                    {
                        "source_id": "gateway",
                        "yaml_url": "https://models.example/v1/models",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                runtime_id="pod-a",
                                base_url="https://pod-a.example",
                                enabled=True,
                            ),
                            SimpleNamespace(
                                runtime_id="pod-b",
                                base_url="https://pod-b.example",
                                enabled=True,
                            ),
                        ]
                    )
                ),
                get_model_discovery_state_store=lambda: Store(),
                get_runtime_http_client=lambda: client,
            ),
        )
        result = await service.refresh(
            cast(KeycloakUser, object()), deps, authorization="Bearer test"
        )

    assert result.refresh_error is None
    assert [
        (item.runtime_id, item.base_url) for item in result.unverified_runtimes
    ] == [("pod-b", "https://pod-b.example")]
    assert result.verified_source_ids == ["gateway"]
    assert result.sources[0].last_error is None
    assert [model.name for model in result.sources[0].available_models] == ["a"]


@pytest.mark.asyncio
async def test_failed_preparation_does_not_activate_or_remove_models(
    monkeypatch,
) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    async def no_names(*args, **kwargs) -> dict[str, str]:
        return {}

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    monkeypatch.setattr(service, "model_display_name_overrides", no_names)
    row = StoredDiscoverySourceState(
        source_id="gateway",
        yaml_url="https://models.example/v1/models",
        override_url=None,
        active_url="https://models.example/v1/models",
        revision=1,
        inventory=[_model("a")],
        removed=[],
        new_ids=[],
        last_success_at=None,
        last_attempt_at=None,
        last_error=None,
    )

    class Store:
        async def get(self, source_id: str) -> StoredDiscoverySourceState:
            return row

        async def list_all(self) -> list[StoredDiscoverySourceState]:
            return [row]

        async def record_failure(
            self, *, source_id: str, yaml_url: str, error: str
        ) -> StoredDiscoverySourceState:
            nonlocal row
            row = replace(row, last_error=error)
            return row

        async def save_success(self, **kwargs) -> None:
            pytest.fail("A failed preparation must not publish an inventory")

    posts: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [_model("a")],
                    "discovery_source_id": "gateway",
                    "discovery_yaml_url": row.yaml_url,
                },
            )
        body = json.loads(request.content)
        posts.append(body)
        if request.url.host == "pod-b.example":
            return httpx.Response(502)
        return httpx.Response(
            200,
            json={
                "models": [_model("b")],
                "discovered_model_ids": ["model__openai__b"],
                "discovery_source_id": "gateway",
                "discovery_effective_url": row.yaml_url,
                "preparation_token": "token-a",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                base_url="https://pod-a.example", enabled=True
                            ),
                            SimpleNamespace(
                                base_url="https://pod-b.example", enabled=True
                            ),
                        ]
                    )
                ),
                get_model_discovery_state_store=lambda: Store(),
                get_runtime_http_client=lambda: client,
            ),
        )
        result = await service.refresh(
            cast(KeycloakUser, object()), deps, authorization="Bearer test"
        )
    assert len(posts) == 2
    assert all(post.get("prepare") is True for post in posts)
    assert result.sources[0].available_models[0].name == "a"
    assert result.sources[0].last_error == "Discovery refresh failed"


@pytest.mark.asyncio
async def test_refresh_recovers_when_a_pod_revision_is_ahead(monkeypatch) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    async def no_names(*args, **kwargs) -> dict[str, str]:
        return {}

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    monkeypatch.setattr(service, "model_display_name_overrides", no_names)
    row = StoredDiscoverySourceState(
        source_id="gateway",
        yaml_url="https://models.example/v1/models",
        override_url=None,
        active_url="https://models.example/v1/models",
        revision=1,
        inventory=[_model("a")],
        removed=[],
        new_ids=[],
        last_success_at=None,
        last_attempt_at=None,
        last_error=None,
    )
    saved_revision = None

    class Store:
        async def get(self, source_id: str) -> StoredDiscoverySourceState:
            return row

        async def list_all(self) -> list[StoredDiscoverySourceState]:
            return [row]

        async def record_failure(self, **kwargs) -> StoredDiscoverySourceState:
            pytest.fail("Recovery should succeed")

        async def save_success(self, **kwargs) -> StoredDiscoverySourceState:
            nonlocal row, saved_revision
            saved_revision = kwargs["applied_revision"]
            row = replace(row, revision=saved_revision, inventory=[_model("b")])
            return row

    activations: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        ahead = request.url.host == "pod-a.example"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [_model("a")],
                    "discovery_source_id": "gateway",
                    "discovery_yaml_url": row.yaml_url,
                },
            )
        body = json.loads(request.content)
        if body.get("prepare"):
            return httpx.Response(
                200,
                json={
                    "models": [_model("b")],
                    "discovered_model_ids": ["model__openai__b"],
                    "discovery_source_id": "gateway",
                    "discovery_effective_url": row.yaml_url,
                    "preparation_token": "token-a" if ahead else "token-b",
                    "active_revision": 3 if ahead else 1,
                },
            )
        activations.append(body["revision"])
        return httpx.Response(200, json={"discovered_model_ids": ["model__openai__b"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                base_url="https://pod-a.example", enabled=True
                            ),
                            SimpleNamespace(
                                base_url="https://pod-b.example", enabled=True
                            ),
                        ]
                    )
                ),
                get_model_discovery_state_store=lambda: Store(),
                get_runtime_http_client=lambda: client,
            ),
        )
        result = await service.refresh(
            cast(KeycloakUser, object()), deps, authorization="Bearer test"
        )
    assert activations == [4, 4]
    assert saved_revision == 4
    assert result.sources[0].available_models[0].name == "b"


@pytest.mark.asyncio
async def test_one_pod_registers_and_refreshes_multiple_sources(monkeypatch) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    async def no_names(*args, **kwargs) -> dict[str, str]:
        return {}

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    monkeypatch.setattr(service, "model_display_name_overrides", no_names)
    rows: dict[str, StoredDiscoverySourceState] = {}

    class Store:
        async def get(self, source_id: str) -> StoredDiscoverySourceState | None:
            return rows.get(source_id)

        async def list_all(self) -> list[StoredDiscoverySourceState]:
            return list(rows.values())

        async def record_failure(self, **kwargs) -> None:
            pytest.fail("Both sources should refresh")

        async def save_success(self, **kwargs) -> StoredDiscoverySourceState:
            source_id = kwargs["source_id"]
            row = StoredDiscoverySourceState(
                source_id=source_id,
                yaml_url=kwargs["yaml_url"],
                override_url=None,
                active_url=kwargs["effective_url"],
                revision=kwargs["applied_revision"],
                inventory=kwargs["inventory"],
                removed=[],
                new_ids=[item["id"] for item in kwargs["inventory"]],
                last_success_at=None,
                last_attempt_at=None,
                last_error=None,
            )
            rows[source_id] = row
            return row

    prepared: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sources = [
            {
                "source_id": source_id,
                "yaml_url": f"https://{source_id}.example/v1/models",
            }
            for source_id in ("east", "west")
        ]
        if request.method == "GET":
            return httpx.Response(
                200, json={"models": [], "discovery_sources": sources}
            )
        body = json.loads(request.content)
        source_id = body.get("source_id")
        if body.get("prepare"):
            prepared.append(source_id)
            model = _model(source_id)
            return httpx.Response(
                200,
                json={
                    "models": [model],
                    "discovery_source_id": source_id,
                    "discovery_effective_url": f"https://{source_id}.example/v1/models",
                    "discovered_model_ids": [model["id"]],
                    "preparation_token": f"token-{source_id}",
                    "active_revision": 0,
                },
            )
        return httpx.Response(
            200,
            json={
                "discovered_model_ids": [
                    _model("east")["id"]
                    if body.get("preparation_token") == "token-east"
                    else _model("west")["id"]
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                base_url="https://pod.example", enabled=True
                            )
                        ]
                    )
                ),
                get_model_discovery_state_store=lambda: Store(),
                get_runtime_http_client=lambda: client,
            ),
        )
        result = await service.refresh(
            cast(KeycloakUser, object()), deps, authorization=None
        )
    assert prepared == ["east", "west"]
    assert {item.source_id for item in result.sources} == {"east", "west"}


@pytest.mark.asyncio
async def test_model_detail_is_proxied_to_the_selected_runtime(monkeypatch) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "chat-a", "max_context_length": 131072})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                runtime_id="pod-a",
                                base_url="https://pod.example",
                                enabled=True,
                            )
                        ]
                    )
                ),
                get_runtime_http_client=lambda: client,
            ),
        )
        detail = await service.get_model_detail(
            cast(KeycloakUser, object()),
            deps,
            source_id="east",
            model_id="chat-a",
            runtime_id="pod-a",
            authorization="Bearer test",
        )
    assert detail["max_context_length"] == 131072
    assert dict(requests[0].url.params) == {"source_id": "east", "model_id": "chat-a"}
    assert requests[0].headers["Authorization"] == "Bearer test"


@pytest.mark.asyncio
async def test_model_detail_tries_another_runtime_when_preferred_is_unavailable(
    monkeypatch,
) -> None:
    async def allowed(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(service, "require_manage_capabilities", allowed)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if request.url.host == "preferred.example":
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "chat-a"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(rebac=object()),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                runtime_id="pod-b",
                                base_url="https://other.example",
                                enabled=True,
                            ),
                            SimpleNamespace(
                                runtime_id="pod-a",
                                base_url="https://preferred.example",
                                enabled=True,
                            ),
                        ]
                    )
                ),
                get_runtime_http_client=lambda: client,
            ),
        )
        detail = await service.get_model_detail(
            cast(KeycloakUser, object()),
            deps,
            source_id="east",
            model_id="chat-a",
            runtime_id="pod-a",
            authorization=None,
        )
    assert detail == {"id": "chat-a"}
    assert requests == ["preferred.example", "other.example"]
