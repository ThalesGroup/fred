# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The abandoned platform default cannot be configured or used by an agent."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fred_capability_ppt_filler.builder import capability
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeWorkspace


@pytest.mark.asyncio
async def test_platform_routes_are_removed():
    app = FastAPI()
    app.include_router(capability._build_router(), prefix="/capabilities/ppt_builder")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for method, path in [
            ("GET", ""),
            ("PUT", "/template"),
            ("DELETE", "/template"),
            ("POST", "/analysis"),
            ("PUT", "/overrides"),
            ("GET", "/patterns.pdf"),
        ]:
            response = await client.request(
                method, f"/capabilities/ppt_builder/platform{path}"
            )
            assert response.status_code == 404


def test_default_tools_use_builtin_without_reading_pod_platform_rows(monkeypatch):
    store = AsyncMock()
    monkeypatch.setattr(capability, "get_analysis_store", lambda: store)
    inventories = []
    monkeypatch.setattr(
        capability,
        "build_builder_tools",
        lambda _ctx, _load, inventory, *_args: inventories.append(inventory) or [],
    )
    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="reader",
            team_id="space",
            agent_instance_id="00000000-0000-4000-8000-000000000007",
        ),
        config=capability.PptBuilderConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(workspace_fs=FakeWorkspace()),
    )
    capability.PptBuilderCapability().middleware(ctx)
    assert inventories == [builtin_template()[1]]
    store.get.assert_not_called()
