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
            source_id="gateway", yaml_url=first.yaml_url, error="timeout"
        )
        assert failed.last_error == "timeout"
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
        assert (
            await ModelDiscoveryStateStore(engine).get("gateway")
        ).effective_url == saved.effective_url
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
            cast(object, object()), deps, authorization="Bearer test"
        )
    assert len(posts) == 2
    assert all(post.get("prepare") is True for post in posts)
    assert result.sources[0].available_models[0].name == "a"
    assert result.sources[0].last_error == "Discovery refresh failed"
