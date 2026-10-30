# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Global packaged skill inventory through the authorized service boundary."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from control_plane_backend.config.models import RuntimeCatalogSourceConfig
from control_plane_backend.platform_skills.service import (
    get_platform_skill_policy,
    get_platform_skills,
    set_platform_skill_enabled,
)
from control_plane_backend.platform_skills.store import PlatformSkillPolicyStore
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fastapi import HTTPException
from fred_core import KeycloakUser
from sqlalchemy.ext.asyncio import AsyncEngine


def _user() -> KeycloakUser:
    return KeycloakUser(uid="manager", username="manager", roles=[], email=None)


@pytest.mark.asyncio
async def test_inventory_merges_only_packaged_skills_and_fetches_sources_concurrently() -> (
    None
):
    started = 0
    ready = asyncio.Event()
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal started
        requests.append(request)
        started += 1
        if started == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=1)
        return httpx.Response(
            200,
            json={
                "policy_supported": True,
                "skills": [
                    {"name": "mermaid", "description": "Draw", "builtin": True},
                    {"name": "custom", "description": "Private", "builtin": False},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        gate = AsyncMock()
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(
                    rebac=SimpleNamespace(check_user_permission_or_raise=gate)
                ),
                get_runtime_http_client=lambda: client,
                get_platform_skill_policy_store=lambda: SimpleNamespace(
                    list_disabled_skill_names=AsyncMock(return_value=set())
                ),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            RuntimeCatalogSourceConfig(
                                runtime_id=name, base_url=f"https://{name}.invalid/v1"
                            )
                            for name in ["pod-b", "pod-a"]
                        ]
                    )
                ),
            ),
        )
        result = await get_platform_skills(
            user=_user(), deps=deps, authorization="Bearer verified"
        )

    assert len(result.skills) == 1
    assert result.skills[0].skill.name == "mermaid"
    assert result.skills[0].enabled is True
    assert result.skills[0].runtime_ids == ["pod-a", "pod-b"]
    assert result.unavailable_runtime_ids == []
    assert result.unsupported_runtime_ids == []
    assert len(requests) == 2
    assert all(request.url.path == "/v1/agents/platform-skills" for request in requests)
    assert all(
        request.headers["Authorization"] == "Bearer verified" for request in requests
    )
    gate.assert_awaited_once()


@pytest.mark.asyncio
async def test_inventory_distinguishes_unavailable_unsupported_empty_and_custom_sources() -> (
    None
):
    responses = {
        "old": httpx.Response(404),
        "unsupported": httpx.Response(200, json={"policy_supported": False}),
        "unreachable": httpx.Response(503),
        "invalid": httpx.Response(200, json={"skills": [{"body": "untrusted"}]}),
        "empty": httpx.Response(200, json={"policy_supported": True, "skills": []}),
        "custom": httpx.Response(
            200,
            json={
                "policy_supported": True,
                "skills": [{"name": "custom", "description": "Custom"}],
            },
        ),
    }
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        name = request.url.host.split(".")[0]
        requests.append(name)
        return responses[name]

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        sources = [
            RuntimeCatalogSourceConfig(
                runtime_id=name, base_url=f"https://{name}.invalid"
            )
            for name in responses
        ]
        sources.append(
            RuntimeCatalogSourceConfig(
                runtime_id="disabled",
                base_url="https://disabled.invalid",
                enabled=False,
            )
        )
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(
                    rebac=SimpleNamespace(check_user_permission_or_raise=AsyncMock())
                ),
                get_runtime_http_client=lambda: client,
                get_platform_skill_policy_store=lambda: SimpleNamespace(
                    list_disabled_skill_names=AsyncMock(return_value=set())
                ),
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(runtime_catalog_sources=sources)
                ),
            ),
        )
        result = await get_platform_skills(user=_user(), deps=deps)

    assert result.skills == []
    assert result.unavailable_runtime_ids == ["invalid", "unreachable"]
    assert result.unsupported_runtime_ids == ["old", "unsupported"]
    assert "disabled" not in requests


@pytest.mark.asyncio
async def test_inventory_denies_before_catalog_or_store_access() -> None:
    gate = AsyncMock(side_effect=HTTPException(status_code=403))
    deps = cast(
        ProductServiceDependencies,
        SimpleNamespace(
            team_dependencies=SimpleNamespace(
                rebac=SimpleNamespace(check_user_permission_or_raise=gate)
            )
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await get_platform_skills(user=_user(), deps=deps)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inventory_retains_disabled_policy_during_source_outage() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as client:
        deps = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(
                    rebac=SimpleNamespace(check_user_permission_or_raise=AsyncMock())
                ),
                get_platform_skill_policy_store=lambda: SimpleNamespace(
                    list_disabled_skill_names=AsyncMock(return_value={"mermaid"})
                ),
                get_runtime_http_client=lambda: client,
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            RuntimeCatalogSourceConfig(
                                runtime_id="pod", base_url="https://pod.invalid"
                            )
                        ]
                    )
                ),
            ),
        )
        result = await get_platform_skills(user=_user(), deps=deps)
    assert result.skills == []
    assert result.disabled_skill_names == ["mermaid"]
    assert result.unavailable_runtime_ids == ["pod"]


def _policy_deps(
    client: httpx.AsyncClient, store: PlatformSkillPolicyStore
) -> ProductServiceDependencies:
    return cast(
        ProductServiceDependencies,
        SimpleNamespace(
            team_dependencies=SimpleNamespace(
                rebac=SimpleNamespace(check_user_permission_or_raise=AsyncMock())
            ),
            get_platform_skill_policy_store=lambda: store,
            get_runtime_http_client=lambda: client,
            configuration=SimpleNamespace(
                platform=SimpleNamespace(
                    runtime_catalog_sources=[
                        RuntimeCatalogSourceConfig(
                            runtime_id="pod", base_url="https://pod.invalid"
                        )
                    ]
                )
            ),
        ),
    )


@pytest.mark.asyncio
async def test_administrator_disables_then_recovers_stored_skill_during_outage(
    control_plane_sql_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []
    status = 200

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status,
            json={
                "policy_supported": True,
                "skills": [{"name": "mermaid", "description": "Draw", "builtin": True}],
            },
        )

    audits: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "control_plane_backend.platform_skills.service.emit_audit_log",
        lambda event, **fields: audits.append((event, fields)),
    )
    store = PlatformSkillPolicyStore(control_plane_sql_engine)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        deps = _policy_deps(client, store)
        disabled = await set_platform_skill_enabled(
            user=_user(), name="mermaid", enabled=False, deps=deps
        )
        assert disabled.model_dump() == {"name": "mermaid", "enabled": False}
        inventory = await get_platform_skills(user=_user(), deps=deps)
        assert inventory.skills[0].enabled is False
        assert inventory.disabled_skill_names == ["mermaid"]
        assert (await get_platform_skill_policy(deps)).disabled_skill_names == [
            "mermaid"
        ]
        status = 503
        before = len(requests)
        enabled = await set_platform_skill_enabled(
            user=_user(), name="mermaid", enabled=True, deps=deps
        )
        assert enabled.enabled is True
        assert len(requests) == before
        assert (await get_platform_skill_policy(deps)).disabled_skill_names == []
        retried = await set_platform_skill_enabled(
            user=_user(), name="mermaid", enabled=True, deps=deps
        )
        assert retried.enabled is True
        assert len(requests) == before
    assert audits == [
        (
            "platform.skill.activation_updated",
            {"actor_uid": "manager", "skill_name": "mermaid", "enabled": False},
        ),
        (
            "platform.skill.activation_updated",
            {"actor_uid": "manager", "skill_name": "mermaid", "enabled": True},
        ),
        (
            "platform.skill.activation_updated",
            {"actor_uid": "manager", "skill_name": "mermaid", "enabled": True},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_status,expected", [(404, 409), (503, 503)])
async def test_disable_refuses_unsupported_or_unreachable_sources(
    control_plane_sql_engine: AsyncEngine, source_status: int, expected: int
) -> None:
    store = PlatformSkillPolicyStore(control_plane_sql_engine)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(source_status))
    ) as client:
        deps = _policy_deps(client, store)
        with pytest.raises(HTTPException) as exc:
            await set_platform_skill_enabled(
                user=_user(), name="mermaid", enabled=False, deps=deps
            )
    assert exc.value.status_code == expected
    assert await store.list_disabled_skill_names() == set()


@pytest.mark.asyncio
async def test_custom_skills_cannot_be_mutated_and_non_managers_cannot_write(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = PlatformSkillPolicyStore(control_plane_sql_engine)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "policy_supported": True,
                    "skills": [{"name": "custom", "description": "Custom"}],
                },
            )
        )
    ) as client:
        deps = _policy_deps(client, store)
        with pytest.raises(HTTPException) as exc:
            await set_platform_skill_enabled(
                user=_user(), name="custom", enabled=False, deps=deps
            )
        assert exc.value.status_code == 404
        denied = cast(
            ProductServiceDependencies,
            SimpleNamespace(
                team_dependencies=SimpleNamespace(
                    rebac=SimpleNamespace(
                        check_user_permission_or_raise=AsyncMock(
                            side_effect=HTTPException(status_code=403)
                        )
                    )
                )
            ),
        )
        with pytest.raises(HTTPException) as exc:
            await set_platform_skill_enabled(
                user=_user(), name="mermaid", enabled=False, deps=denied
            )
        assert exc.value.status_code == 403
    assert await store.list_disabled_skill_names() == set()
