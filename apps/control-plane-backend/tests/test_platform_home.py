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

"""Home page mode and admin-ordered featured agents: store, admin service, user read."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.platform_ui_settings.schemas import (
    SetPlatformHomeRequest,
    UnknownFeaturedAgentError,
)
from control_plane_backend.platform_ui_settings.service import (
    get_platform_home,
    set_platform_home,
)
from control_plane_backend.platform_ui_settings.store import (
    PlatformUiSettingsStore,
    StoredFeaturedAgent,
)
from control_plane_backend.product import home_agents
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.home_agents import get_home_showcase
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacDisabledResult
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

DEFAULT_TEAM = "everyone"
OTHER_TEAM = "hr"


async def _add_agent(
    engine: AsyncEngine,
    agent_id: str,
    *,
    team_id: str = DEFAULT_TEAM,
    enabled: bool = True,
    suspension_reason: str | None = None,
) -> None:
    async with async_sessionmaker(engine)() as session, session.begin():
        session.add(
            AgentInstanceRow(
                agent_instance_id=agent_id,
                team_id=team_id,
                template_id="tpl",
                source_runtime_id="rt",
                source_agent_id="src",
                display_name=f"Agent {agent_id}",
                enabled=enabled,
                suspension_reason=suspension_reason,
            )
        )


class _Rebac:
    def __init__(self, *, admin: bool = True, usable: list[str] | None = None):
        self._admin = admin
        self._usable = usable

    async def check_user_permission_or_raise(self, user, permission, *args, **kw):
        if not (
            self._admin and permission == OrganizationPermission.CAN_MANAGE_PLATFORM
        ):
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )

    async def lookup_user_resources(self, user, permission):
        if self._usable is None:
            return RebacDisabledResult()
        return [SimpleNamespace(id=team_id) for team_id in self._usable]


def _deps(engine: AsyncEngine, rebac: _Rebac) -> ProductServiceDependencies:
    ui_store = PlatformUiSettingsStore(engine)
    agent_store = AgentInstanceStore(engine)
    names = {DEFAULT_TEAM: SimpleNamespace(name="Everyone")}
    teams = SimpleNamespace(
        rebac=rebac,
        get_default_team_store=lambda: SimpleNamespace(
            list_team_ids=AsyncMock(return_value=[DEFAULT_TEAM])
        ),
        get_team_metadata_store=lambda: SimpleNamespace(
            get_by_team_ids=AsyncMock(
                side_effect=lambda ids: {i: names[i] for i in ids if i in names}
            ),
            list_all=AsyncMock(
                return_value=[
                    SimpleNamespace(id=DEFAULT_TEAM),
                    SimpleNamespace(id=OTHER_TEAM),
                ]
            ),
        ),
    )
    runtime = SimpleNamespace(runtime_id="rt", enabled=True, base_url="http://rt")
    fake = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(runtime_catalog_sources=[runtime])
        ),
        team_dependencies=teams,
        get_platform_ui_settings_store=lambda: ui_store,
        get_agent_instance_store=lambda: agent_store,
    )
    return cast(ProductServiceDependencies, fake)


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=[], email=None)


@pytest.fixture(autouse=True)
def pod_limit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The pod read behind the question field limit; offline in every test."""
    read = AsyncMock(return_value=([], 4000))
    monkeypatch.setattr(home_agents, "_runtime_execution_metadata_for_source", read)
    return read


@pytest_asyncio.fixture
async def engine(control_plane_sql_engine: AsyncEngine) -> AsyncEngine:
    for agent_id in ("a", "b", "c"):
        await _add_agent(control_plane_sql_engine, agent_id)
    await _add_agent(control_plane_sql_engine, "off", enabled=False)
    await _add_agent(
        control_plane_sql_engine, "susp", suspension_reason="capability_pending"
    )
    await _add_agent(control_plane_sql_engine, "hr", team_id=OTHER_TEAM)
    return control_plane_sql_engine


@pytest.mark.asyncio
async def test_store_defaults_to_classic_and_keeps_order_and_themes(
    engine: AsyncEngine,
) -> None:
    store = PlatformUiSettingsStore(engine)
    empty = await store.get_home()
    assert (empty.layout, empty.featured) == ("classic", [])

    await store.set(default_theme="cobalt", hidden_themes=[], updated_by="x")
    await store.set_home(
        layout="advanced",
        featured=[
            StoredFeaturedAgent("c", "Nouveau", ["Résume"]),
            StoredFeaturedAgent("a", None, []),
        ],
        ask_agent_instance_id=None,
        updated_by="x",
    )
    # Saving themes again must not reset the home mode, and vice versa.
    await store.set(default_theme="pebble", hidden_themes=[], updated_by="x")
    home = await store.get_home()
    themes = await store.get()
    assert home.layout == "advanced"
    assert [f.agent_instance_id for f in home.featured] == ["c", "a"]
    assert home.featured[0].badge == "Nouveau"
    assert home.featured[0].highlights == ["Résume"]
    assert themes is not None and themes.default_theme == "pebble"

    await store.set_home(
        layout="classic", featured=[], ask_agent_instance_id=None, updated_by="x"
    )
    assert (await store.get_home()).featured == []


@pytest.mark.parametrize(
    "payload",
    [
        {"layout": "fancy"},
        {"featured": [{"agent_instance_id": "a"}, {"agent_instance_id": "a"}]},
        {"featured": [{"agent_instance_id": f"a{i}"} for i in range(11)]},
        {"featured": [{"agent_instance_id": "a", "badge": "x" * 21}]},
        {"featured": [{"agent_instance_id": "a", "highlights": ["h"] * 5}]},
        {"featured": [{"agent_instance_id": "a", "highlights": ["x" * 81]}]},
        {"featured": [{"agent_instance_id": "a", "highlights": ["  "]}]},
        {"layout": "classic", "extra": 1},
        {"ask_agent_instance_id": ""},
    ],
)
def test_request_rejects_malformed_home(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SetPlatformHomeRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_non_admin_can_neither_read_nor_write(engine: AsyncEngine) -> None:
    deps = _deps(engine, _Rebac(admin=False))
    with pytest.raises(AuthorizationError):
        await get_platform_home(user=_user(), deps=deps)
    with pytest.raises(AuthorizationError):
        await set_platform_home(
            user=_user(), request=SetPlatformHomeRequest(layout="advanced"), deps=deps
        )
    assert (await PlatformUiSettingsStore(engine).get_home()).layout == "classic"


@pytest.mark.asyncio
async def test_admin_sees_candidates_and_unavailable_entries(
    engine: AsyncEngine,
) -> None:
    deps = _deps(engine, _Rebac())
    saved = await set_platform_home(
        user=_user(),
        request=SetPlatformHomeRequest.model_validate(
            {
                "layout": "advanced",
                "featured": [
                    {"agent_instance_id": "b", "badge": " Populaire "},
                    {"agent_instance_id": "off"},
                    {"agent_instance_id": "hr"},
                ],
            }
        ),
        deps=deps,
    )
    assert [(f.agent_instance_id, f.available) for f in saved.featured] == [
        ("b", True),
        ("off", False),
        ("hr", False),
    ]
    assert saved.featured[0].badge == "Populaire"
    assert saved.featured[0].team_name == "Everyone"
    # Only enabled, unsuspended agents of default teams can be added.
    assert [c.agent_instance_id for c in saved.candidates] == ["a", "b", "c"]
    # SQLite reads the timestamp back without its timezone: compare the rest.
    reread = await get_platform_home(user=_user(), deps=deps)
    assert reread.model_dump(exclude={"updated_at"}) == saved.model_dump(
        exclude={"updated_at"}
    )


@pytest.mark.asyncio
async def test_admin_cannot_save_an_unknown_agent(engine: AsyncEngine) -> None:
    deps = _deps(engine, _Rebac())
    for payload in (
        {"featured": [{"agent_instance_id": "ghost"}]},
        {"ask_agent_instance_id": "ghost"},
    ):
        with pytest.raises(UnknownFeaturedAgentError):
            await set_platform_home(
                user=_user(),
                request=SetPlatformHomeRequest.model_validate(payload),
                deps=deps,
            )


@pytest.mark.asyncio
async def test_user_sees_only_usable_featured_agents_in_order(
    engine: AsyncEngine,
) -> None:
    store = PlatformUiSettingsStore(engine)
    await store.set_home(
        layout="advanced",
        featured=[
            StoredFeaturedAgent(agent_id, None, [])
            for agent_id in ("c", "off", "susp", "hr", "a", "ghost")
        ],
        ask_agent_instance_id=None,
        updated_by="x",
    )
    member = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[DEFAULT_TEAM]))
    )
    assert member.layout == "advanced"
    assert [f.agent.agent_instance_id for f in member.featured] == ["c", "a"]

    outsider = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[OTHER_TEAM]))
    )
    assert outsider.featured == []

    no_rebac = await get_home_showcase(_user(), _deps(engine, _Rebac(usable=None)))
    assert [f.agent.agent_instance_id for f in no_rebac.featured] == ["c", "a"]


@pytest.mark.asyncio
async def test_classic_or_unknown_layout_returns_no_carousel(
    engine: AsyncEngine,
) -> None:
    store = PlatformUiSettingsStore(engine)
    await store.set_home(
        layout="classic",
        featured=[StoredFeaturedAgent("a", None, [])],
        ask_agent_instance_id="a",
        updated_by="x",
    )
    classic = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[DEFAULT_TEAM]))
    )
    assert (classic.layout, classic.featured, classic.ask_agent) == (
        "classic",
        [],
        None,
    )

    await store.set_home(
        layout="from-a-newer-release",
        featured=[StoredFeaturedAgent("a", None, [])],
        ask_agent_instance_id=None,
        updated_by="x",
    )
    unknown = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[DEFAULT_TEAM]))
    )
    assert unknown.layout == "classic"


@pytest.mark.asyncio
async def test_question_agent_is_saved_apart_from_the_carousel(
    engine: AsyncEngine,
) -> None:
    deps = _deps(engine, _Rebac())
    saved = await set_platform_home(
        user=_user(),
        request=SetPlatformHomeRequest.model_validate(
            {"layout": "advanced", "ask_agent_instance_id": "b"}
        ),
        deps=deps,
    )
    assert saved.featured == []
    assert saved.ask_agent is not None
    assert (saved.ask_agent.agent_instance_id, saved.ask_agent.available) == ("b", True)

    hidden = await set_platform_home(
        user=_user(),
        request=SetPlatformHomeRequest.model_validate(
            {"layout": "advanced", "ask_agent_instance_id": "off"}
        ),
        deps=deps,
    )
    assert hidden.ask_agent is not None and hidden.ask_agent.available is False

    cleared = await set_platform_home(
        user=_user(),
        request=SetPlatformHomeRequest.model_validate({"layout": "advanced"}),
        deps=deps,
    )
    assert cleared.ask_agent is None


@pytest.mark.asyncio
async def test_user_gets_the_question_agent_only_when_usable(
    engine: AsyncEngine,
) -> None:
    store = PlatformUiSettingsStore(engine)
    # No carousel: the question field still has its agent.
    await store.set_home(
        layout="advanced", featured=[], ask_agent_instance_id="b", updated_by="x"
    )
    member = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[DEFAULT_TEAM]))
    )
    assert member.featured == []
    assert member.ask_agent is not None and member.ask_agent.agent_instance_id == "b"

    outsider = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[OTHER_TEAM]))
    )
    assert outsider.ask_agent is None

    for unusable in ("off", "susp", "hr"):
        await store.set_home(
            layout="advanced",
            featured=[],
            ask_agent_instance_id=unusable,
            updated_by="x",
        )
        shown = await get_home_showcase(
            _user(), _deps(engine, _Rebac(usable=[DEFAULT_TEAM, OTHER_TEAM]))
        )
        assert shown.ask_agent is None


@pytest.mark.asyncio
async def test_question_limit_comes_from_the_agent_pod_and_never_blocks(
    engine: AsyncEngine, pod_limit: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await PlatformUiSettingsStore(engine).set_home(
        layout="advanced", featured=[], ask_agent_instance_id="b", updated_by="x"
    )
    deps = _deps(engine, _Rebac(usable=[DEFAULT_TEAM]))
    assert (await get_home_showcase(_user(), deps)).ask_max_chat_input_chars == 4000
    pod_limit.assert_awaited_once_with("http://rt")

    async def slow(_base_url: str) -> tuple[list, int]:
        await asyncio.sleep(1)
        return [], 4000

    monkeypatch.setattr(home_agents, "_runtime_execution_metadata_for_source", slow)
    monkeypatch.setattr(home_agents, "ASK_LIMIT_TIMEOUT_SECONDS", 0.01)
    late = await get_home_showcase(_user(), deps)
    assert late.ask_agent is not None and late.ask_max_chat_input_chars is None

    # No question agent usable by the caller: no pod read at all.
    pod_limit.reset_mock()
    monkeypatch.setattr(
        home_agents, "_runtime_execution_metadata_for_source", pod_limit
    )
    outsider = await get_home_showcase(
        _user(), _deps(engine, _Rebac(usable=[OTHER_TEAM]))
    )
    assert outsider.ask_max_chat_input_chars is None
    pod_limit.assert_not_awaited()
