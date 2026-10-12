# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Managed skill catalog authorization and source isolation."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from control_plane_backend.product import api
from control_plane_backend.product.service import ExecutionPreparationError
from control_plane_backend.product.skills import get_instance_skills
from fastapi import HTTPException, Request
from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId


@pytest.mark.asyncio
@pytest.mark.parametrize("hint", [None, "[meeting notes]"])
async def test_catalog_uses_only_selected_source_and_forwards_identity(
    hint: str | None,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "supported": True,
                "revision": "snapshot",
                "skills": [
                    {
                        "name": "minutes",
                        "description": "Write minutes",
                        **({"argument_hint": hint} if hint else {}),
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        store = SimpleNamespace(
            get_for_team=AsyncMock(
                return_value=SimpleNamespace(
                    enabled=True, suspension_reason=None, source_runtime_id="selected"
                )
            )
        )
        sources = [
            SimpleNamespace(
                enabled=True, runtime_id="other", base_url="https://other.invalid"
            ),
            SimpleNamespace(
                enabled=True,
                runtime_id="selected",
                base_url="https://selected.invalid/runtime/v1/",
            ),
        ]
        deps = cast(
            Any,
            SimpleNamespace(
                get_agent_instance_store=lambda: store,
                get_runtime_http_client=lambda: client,
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(runtime_catalog_sources=sources)
                ),
            ),
        )
        catalog = await get_instance_skills(
            TeamId("team"), "instance", deps, "Bearer verified"
        )
        assert len(requests) == 1
        assert (
            str(requests[0].url)
            == "https://selected.invalid/runtime/v1/agents/skills?agent_instance_id=instance&team_id=team"
        )
        assert requests[0].headers["Authorization"] == "Bearer verified"
        store.get_for_team.assert_awaited_once_with("instance", TeamId("team"))
        assert catalog.model_dump()["skills"] == (
            {"name": "minutes", "description": "Write minutes", "argument_hint": hint},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,expected",
    [
        (404, {}, False),
        (
            200,
            {
                "supported": True,
                "skills": [
                    {"name": "minutes", "description": "Write", "body": "SECRET"}
                ],
            },
            None,
        ),
    ],
)
async def test_older_runtime_or_invalid_metadata(
    status: int, body: dict[str, Any], expected: bool | None
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    ) as client:
        deps = cast(
            Any,
            SimpleNamespace(
                get_agent_instance_store=lambda: SimpleNamespace(
                    get_for_team=AsyncMock(
                        return_value=SimpleNamespace(
                            enabled=True,
                            suspension_reason=None,
                            source_runtime_id="pod",
                        )
                    )
                ),
                get_runtime_http_client=lambda: client,
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                enabled=True,
                                runtime_id="pod",
                                base_url="https://pod.invalid",
                            )
                        ]
                    )
                ),
            ),
        )
        if expected is None:
            with pytest.raises(ExecutionPreparationError) as exc:
                await get_instance_skills(TeamId("team"), "instance", deps)
            assert exc.value.http_status == 502
        else:
            assert (
                await get_instance_skills(TeamId("team"), "instance", deps)
            ).supported is expected


@pytest.mark.asyncio
async def test_catalog_team_use_denied_before_any_runtime_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = AsyncMock(side_effect=HTTPException(status_code=403))
    monkeypatch.setattr(api, "require_team_access", gate)
    deps = cast(Any, SimpleNamespace(team_dependencies=object()))
    user = KeycloakUser(uid="user", username="user", roles=[], email=None)
    with pytest.raises(HTTPException) as exc:
        await api.get_agent_instance_skills(
            TeamId("team"),
            "instance",
            deps,
            Request({"type": "http", "headers": []}),
            user,
        )
    assert exc.value.status_code == 403
    assert gate.await_args is not None
    assert gate.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_USE_TEAM_AGENTS
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,status,expected",
    [("minutes", 200, 200), ("other", 200, 502), ("minutes", 404, 404)],
)
async def test_skill_detail_selected_source_identity_and_validation(
    name: str, status: int, expected: int
) -> None:
    from control_plane_backend.product.skills import get_instance_skill_detail

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status,
            json={
                "skill": {"name": name, "description": "Write minutes"},
                "revision": "startup",
                "content": "# Procedure",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        store = SimpleNamespace(
            get_for_team=AsyncMock(
                return_value=SimpleNamespace(
                    enabled=True, suspension_reason=None, source_runtime_id="selected"
                )
            )
        )
        deps = cast(
            Any,
            SimpleNamespace(
                get_agent_instance_store=lambda: store,
                get_runtime_http_client=lambda: client,
                configuration=SimpleNamespace(
                    platform=SimpleNamespace(
                        runtime_catalog_sources=[
                            SimpleNamespace(
                                enabled=True,
                                runtime_id="other",
                                base_url="https://other.invalid",
                            ),
                            SimpleNamespace(
                                enabled=True,
                                runtime_id="selected",
                                base_url="https://selected.invalid/runtime/v1",
                            ),
                        ]
                    )
                ),
            ),
        )
        if expected == 200:
            detail = await get_instance_skill_detail(
                TeamId("team"), "instance", "minutes", deps, "Bearer verified"
            )
            assert detail.content == "# Procedure"
        else:
            with pytest.raises(ExecutionPreparationError) as exc:
                await get_instance_skill_detail(
                    TeamId("team"), "instance", "minutes", deps, "Bearer verified"
                )
            assert exc.value.http_status == expected
        assert len(requests) == 1
        assert requests[0].url.path == "/runtime/v1/agents/skills/minutes"
        assert dict(requests[0].url.params) == {
            "agent_instance_id": "instance",
            "team_id": "team",
        }
        assert requests[0].headers["Authorization"] == "Bearer verified"
        with pytest.raises(ExecutionPreparationError) as exc:
            await get_instance_skill_detail(
                TeamId("team"), "instance", "../minutes", deps
            )
        assert exc.value.http_status == 422
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_skill_detail_team_use_denied_before_runtime_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = AsyncMock(side_effect=HTTPException(status_code=403))
    monkeypatch.setattr(api, "require_team_access", gate)
    deps = cast(Any, SimpleNamespace(team_dependencies=object()))
    user = KeycloakUser(uid="user", username="user", roles=[], email=None)
    with pytest.raises(HTTPException) as exc:
        await api.get_agent_instance_skill_detail(
            TeamId("team"),
            "instance",
            "minutes",
            deps,
            Request({"type": "http", "headers": []}),
            user,
        )
    assert exc.value.status_code == 403
    assert gate.await_args is not None
    assert gate.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_USE_TEAM_AGENTS
    ]
