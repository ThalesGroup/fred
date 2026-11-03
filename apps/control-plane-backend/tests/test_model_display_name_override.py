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

import pytest
from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.capabilities.catalog import aggregate_capability_catalog
from control_plane_backend.capabilities.display_name_store import (
    ModelDisplayNameOverrideStore,
)
from control_plane_backend.capabilities.enablement import CapabilityNotFound
from control_plane_backend.capabilities.schemas import SetModelDisplayNameRequest
from control_plane_backend.models.base import Base
from control_plane_backend.models.model_display_name_models import (
    ModelDisplayNameOverrideRow,
)
from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.service import PodModelCatalog
from fred_core import KeycloakUser
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

MODEL_ID = "model__openai__discovered.gateway.abc"


def _model_entry(display_name: str | None = "Gateway Chat") -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=MODEL_ID,
        version="1",
        name="chat-a",
        description="chat-a",
        icon="neurology",
        kind="model",
        model_display_name=display_name,
        model_chat_profile_ids=("discovered.chat.gateway.abc",),
    )


@pytest.mark.asyncio
async def test_store_persists_and_clears_a_name() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        Base.metadata.tables[ModelDisplayNameOverrideRow.__tablename__]
                    ],
                )
            )
        store = ModelDisplayNameOverrideStore(engine)
        assert await store.list_all() == {}
        await store.set(
            model_capability_id=MODEL_ID,
            display_name="Team Chat",
            updated_by="admin-1",
        )
        assert await ModelDisplayNameOverrideStore(engine).list_all() == {
            MODEL_ID: "Team Chat"
        }
        await store.set(
            model_capability_id=MODEL_ID,
            display_name="Other Chat",
            updated_by="admin-2",
        )
        assert await store.list_all() == {MODEL_ID: "Other Chat"}
        await store.set(
            model_capability_id=MODEL_ID,
            display_name=None,
            updated_by="admin-2",
        )
        assert await store.list_all() == {}
    finally:
        await engine.dispose()


@pytest.mark.parametrize("name", ["", "  ", "bad\nname", "x" * 161])
def test_invalid_display_names_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        SetModelDisplayNameRequest(display_name=name)


@pytest.mark.asyncio
async def test_admin_write_requires_a_model_and_preserves_wire_name(
    monkeypatch,
) -> None:
    calls: list[str] = []

    async def gate(_rebac, _user, capability_id, *, deps):
        calls.append(f"gate:{capability_id}")

    async def catalog(_deps):
        calls.append("catalog")
        return {
            MODEL_ID: _model_entry(),
            "tool": CapabilityCatalogEntry(
                id="tool", version="1", name="tool", description="tool", icon="tune"
            ),
        }

    class Store:
        async def set(self, *, model_capability_id, display_name, updated_by):
            calls.append(f"store:{model_capability_id}:{display_name}:{updated_by}")

    monkeypatch.setattr(capability_service, "_require_can_manage", gate)
    monkeypatch.setattr(capability_service, "aggregate_capability_catalog", catalog)
    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(rebac=object()),
        get_model_display_name_override_store=lambda: Store(),
    )
    user = KeycloakUser(uid="admin-1", username="admin-1", roles=["admin"], email=None)
    result = await capability_service.set_model_display_name(
        user=user,
        capability_id=MODEL_ID,
        display_name=" Team Chat ",
        deps=cast(ProductServiceDependencies, deps),
    )
    assert result.display_name == "Team Chat"
    assert calls == [
        f"gate:{MODEL_ID}",
        "catalog",
        f"store:{MODEL_ID}:Team Chat:admin-1",
    ]
    assert _model_entry().name == "chat-a"

    with pytest.raises(CapabilityNotFound):
        await capability_service.set_model_display_name(
            user=user,
            capability_id="tool",
            display_name="Tool",
            deps=cast(ProductServiceDependencies, deps),
        )
    assert not any(call.startswith("store:tool") for call in calls)


@pytest.mark.asyncio
async def test_aggregated_model_label_prefers_saved_name_and_restores_gateway_name(
    monkeypatch,
) -> None:
    saved: dict[str, str] = {MODEL_ID: "Team Chat"}

    async def tools(_base_url):
        return []

    async def agents(_base_url, _runtime_id):
        return []

    async def models(_base_url):
        return PodModelCatalog(entries=[_model_entry()])

    async def knowledge_bases():
        return []

    class Store:
        async def list_all(self):
            return dict(saved)

    monkeypatch.setattr(product_service, "_available_capabilities_for_source", tools)
    monkeypatch.setattr(product_service, "_agent_capabilities_for_source", agents)
    monkeypatch.setattr(product_service, "_model_capabilities_for_source", models)
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                frontend=SimpleNamespace(
                    feature_flags=SimpleNamespace(enableApplications=False)
                ),
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod", runtime_id="pod"
                    )
                ],
            )
        ),
        get_knowledge_base_definition_store=lambda: SimpleNamespace(
            list_all=knowledge_bases
        ),
        get_model_display_name_override_store=lambda: Store(),
    )

    first = await aggregate_capability_catalog(cast(ProductServiceDependencies, deps))
    assert first[MODEL_ID].model_display_name == "Team Chat"
    assert first[MODEL_ID].name == "chat-a"
    saved.clear()
    second = await aggregate_capability_catalog(cast(ProductServiceDependencies, deps))
    assert second[MODEL_ID].model_display_name == "Gateway Chat"
