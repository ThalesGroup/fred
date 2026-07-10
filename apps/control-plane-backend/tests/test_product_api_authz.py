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

"""AUTHZ-05 review items 1a/1b: wiring checks for `product/api.py`.

These endpoints call `get_team_by_id_from_service` to gate access. Before this
fix, five prompt mutation endpoints and two agent-listing GETs omitted
`required_permissions` and silently fell back to `CAN_READ` (`team_member or
public`), letting any visitor of a public team mutate prompts or enumerate
non-public agents. These tests lock the correct `required_permissions` down at
the wiring level.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from control_plane_backend.product import api as product_api
from control_plane_backend.product.schemas import (
    CreatePromptRequest,
    PromptPromoteRequest,
    PromptScoreUpdateRequest,
    UpdatePromptRequest,
)
from fred_core import KeycloakUser, OrganizationPermission, TeamPermission
from fred_core.common import TeamId


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=["viewer"], email=None, groups=[])


class _FakeTeam:
    id = TeamId("bid-and-capture")


class _FakeRebac:
    def __init__(self, *, can_manage_platform: bool) -> None:
        self.can_manage_platform = can_manage_platform
        self.calls: list[tuple[Any, ...]] = []

    async def has_user_permission(
        self, user: Any, permission: Any, resource_id: Any
    ) -> bool:
        self.calls.append((user, permission, resource_id))
        return self.can_manage_platform


@pytest.fixture(autouse=True)
def _stub_service_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every downstream service call so only the authz wiring is exercised.

    Non-None sentinels for the endpoints that 404 on a `None`/falsy result.
    """
    for name, return_value in (
        ("create_prompt", object()),
        ("update_prompt", object()),
        ("delete_prompt", True),
        ("promote_prompt", object()),
        ("update_prompt_score", object()),
        ("list_agent_templates", []),
        ("list_managed_agent_instances", []),
    ):
        monkeypatch.setattr(product_api, name, AsyncMock(return_value=return_value))


@pytest.mark.parametrize(
    "endpoint_name,call",
    [
        (
            "post_team_prompt",
            lambda deps, user: product_api.post_team_prompt(
                TeamId("t"),
                CreatePromptRequest(name="n", text="t"),
                deps,
                user,
            ),
        ),
        (
            "put_team_prompt",
            lambda deps, user: product_api.put_team_prompt(
                TeamId("t"),
                "p",
                UpdatePromptRequest(name="n", text="t"),
                deps,
                user,
            ),
        ),
        (
            "delete_team_prompt",
            lambda deps, user: product_api.delete_team_prompt(
                TeamId("t"), "p", deps, user
            ),
        ),
        (
            "post_promote_prompt",
            lambda deps, user: product_api.post_promote_prompt(
                TeamId("t"),
                "p",
                PromptPromoteRequest(target_team_id="other"),
                deps,
                user,
            ),
        ),
        (
            "patch_team_prompt",
            lambda deps, user: product_api.patch_team_prompt(
                TeamId("t"),
                "p",
                PromptScoreUpdateRequest(score=4.5),
                deps,
                user,
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_prompt_mutation_endpoints_require_can_update_resources(
    monkeypatch: pytest.MonkeyPatch, endpoint_name: str, call: Any
) -> None:
    """Item 1a: prompt mutation endpoints must require CAN_UPDATE_RESOURCES,
    not silently fall back to CAN_READ (team_member or public)."""
    get_team = AsyncMock(return_value=_FakeTeam())
    monkeypatch.setattr(product_api, "get_team_by_id_from_service", get_team)

    deps = cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace()))
    await call(deps, _user())

    assert get_team.await_args is not None
    assert get_team.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_UPDATE_RESOURCES
    ]


@pytest.mark.asyncio
async def test_get_agent_templates_requires_can_use_team_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item 1b: listing agent templates must require CAN_USE_TEAM_AGENTS
    (team_member only), not the default CAN_READ (which also admits `public`)."""
    get_team = AsyncMock(return_value=_FakeTeam())
    monkeypatch.setattr(product_api, "get_team_by_id_from_service", get_team)

    rebac = _FakeRebac(can_manage_platform=False)
    deps = cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace(rebac=rebac)))

    await product_api.get_team_agent_templates(TeamId("t"), deps, _user())

    assert get_team.await_args is not None
    assert get_team.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_USE_TEAM_AGENTS
    ]


@pytest.mark.asyncio
async def test_get_agent_instances_requires_can_use_team_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_team = AsyncMock(return_value=_FakeTeam())
    monkeypatch.setattr(product_api, "get_team_by_id_from_service", get_team)

    deps = cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace()))
    await product_api.get_team_agent_instances(TeamId("t"), deps, _user())

    assert get_team.await_args is not None
    assert get_team.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_USE_TEAM_AGENTS
    ]


@pytest.mark.asyncio
async def test_include_non_public_requires_real_openfga_platform_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item 1b: `include_non_public=true` must only be honored for an OpenFGA
    `platform_admin`/`platform_observer` (via CAN_MANAGE_PLATFORM), never for a
    bare Keycloak `admin` role."""
    monkeypatch.setattr(
        product_api, "get_team_by_id_from_service", AsyncMock(return_value=_FakeTeam())
    )
    list_templates = AsyncMock(return_value=[])
    monkeypatch.setattr(product_api, "list_agent_templates", list_templates)

    # A Keycloak `admin` role with no OpenFGA platform_admin relation: denied.
    rebac_denied = _FakeRebac(can_manage_platform=False)
    deps_denied = cast(
        Any, SimpleNamespace(team_dependencies=SimpleNamespace(rebac=rebac_denied))
    )
    admin_user = KeycloakUser(
        uid="u", username="u", roles=["admin"], email=None, groups=[]
    )
    await product_api.get_team_agent_templates(
        TeamId("t"), deps_denied, admin_user, include_non_public=True
    )
    assert list_templates.await_args is not None
    assert list_templates.await_args.kwargs["include_non_public"] is False
    assert rebac_denied.calls[0][1] == OrganizationPermission.CAN_MANAGE_PLATFORM

    # A real OpenFGA platform_admin: honored.
    rebac_allowed = _FakeRebac(can_manage_platform=True)
    deps_allowed = cast(
        Any, SimpleNamespace(team_dependencies=SimpleNamespace(rebac=rebac_allowed))
    )
    await product_api.get_team_agent_templates(
        TeamId("t"), deps_allowed, admin_user, include_non_public=True
    )
    assert list_templates.await_args is not None
    assert list_templates.await_args.kwargs["include_non_public"] is True
