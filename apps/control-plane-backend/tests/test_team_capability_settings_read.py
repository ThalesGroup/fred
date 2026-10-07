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

"""Reading a team's effective capability settings.

The store has always been readable; nothing exposed it. Two surfaces now do —
the admin form seeding an already-enabled team, and a team's own members, who
need the posture a capability's runtime behaviour depends on. Both resolve the
same effective values: declared defaults overlaid with what the team stored,
restricted to the keys the manifest still declares.
"""

# pyright: reportArgumentType=false
# ^ same convention as test_capability_enablement_1980: lightweight fakes and
#   raw str team ids are passed into functions typed against real protocols.
from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import no_knowledge_base_store
from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.capabilities.service import _effective_team_settings
from control_plane_backend.capabilities.settings_store import (
    PERSONAL_SCOPE_SETTINGS_ID,
    TeamCapabilitySettings,
)
from control_plane_backend.product import service as product_service
from control_plane_backend.product.service import PodModelCatalog
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy
from fred_sdk.contracts.models import FieldSpec

CAPABILITY_ID = "html_artifact"

JS_FIELD = FieldSpec(
    key="allow_javascript",
    type="boolean",
    title="Allow JavaScript",
    default=False,
)


def _entry(fields: list[FieldSpec] | None = None) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=CAPABILITY_ID,
        version="0.2.0",
        name="capability.html_artifact.name",
        description="capability.html_artifact.description",
        icon="code",
        team_scope=TeamScopePolicy.ADMIN_GATED,
        team_settings_fields=fields if fields is not None else [JS_FIELD],
    )


class _SettingsStore:
    def __init__(self, stored: dict | None, by_team: dict | None = None) -> None:
        self._stored = stored
        self._by_team = by_team or {}
        self.seen: list[tuple[str, str]] = []
        self.upserts: list[tuple] = []

    async def list_for_capability(self, capability_id: str):
        return dict(self._by_team)

    async def upsert(self, *, team_id, capability_id, settings, updated_by):
        self.upserts.append((str(team_id), capability_id, settings, updated_by))
        return None

    async def get(self, *, team_id, capability_id):
        self.seen.append((str(team_id), capability_id))
        if self._stored is None:
            return None
        return TeamCapabilitySettings(
            team_id=team_id,
            capability_id=capability_id,
            settings=self._stored,
            updated_by="u-admin",
            updated_at=None,
        )


def _deps(store: _SettingsStore, entry: CapabilityCatalogEntry) -> SimpleNamespace:
    return SimpleNamespace(
        get_knowledge_base_definition_store=no_knowledge_base_store,
        get_team_capability_settings_store=lambda: store,
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                frontend=SimpleNamespace(
                    feature_flags=SimpleNamespace(enableApplications=False)
                ),
                application_sources=[],
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod", runtime_id="runtime-a"
                    )
                ],
            )
        ),
    )


@pytest.fixture
def _pod_catalog(monkeypatch):
    """Serve one capability entry from a single fake pod."""

    entries: list[CapabilityCatalogEntry] = []

    async def _fetch(base_url: str):
        return entries

    async def _fetch_agents(base_url: str, runtime_id: str):
        return []

    async def _fetch_models(base_url: str):
        return PodModelCatalog(entries=[])

    monkeypatch.setattr(product_service, "_available_capabilities_for_source", _fetch)
    monkeypatch.setattr(
        product_service, "_agent_capabilities_for_source", _fetch_agents
    )
    monkeypatch.setattr(
        product_service, "_model_capabilities_for_source", _fetch_models
    )
    return entries


# --- effective value resolution ---


def test_absent_row_yields_the_declared_default():
    assert _effective_team_settings(_entry(), None) == {"allow_javascript": False}


def test_stored_value_overrides_the_default():
    assert _effective_team_settings(_entry(), {"allow_javascript": True}) == {
        "allow_javascript": True
    }


def test_stored_false_is_not_mistaken_for_absent():
    """`False` is a value, not a missing key — a `or default` would flip it."""

    assert _effective_team_settings(_entry(), {"allow_javascript": False}) == {
        "allow_javascript": False
    }


def test_undeclared_stored_key_is_dropped():
    """A row left by an older manifest cannot leak a field that no longer exists."""

    stored = {
        "allow_javascript": True,
        "retired_secret": "s3cret",  # pragma: allowlist secret
    }

    assert _effective_team_settings(_entry(), stored) == {"allow_javascript": True}


def test_capability_without_settings_returns_nothing():
    assert _effective_team_settings(_entry(fields=[]), {"stray": 1}) == {}


def test_field_without_default_is_omitted_when_unset():
    field = FieldSpec(key="label", type="string", title="Label")

    assert _effective_team_settings(_entry(fields=[field]), None) == {}
    assert _effective_team_settings(_entry(fields=[field]), {"label": "x"}) == {
        "label": "x"
    }


# --- the read path end to end ---


@pytest.mark.asyncio
async def test_read_returns_defaults_for_a_team_with_no_row(_pod_catalog):
    _pod_catalog.append(_entry())
    store = _SettingsStore(None)

    view = await capability_service.read_team_capability_settings(
        capability_id=CAPABILITY_ID,
        team_id="team-a",
        deps=_deps(store, _entry()),
    )

    assert view.capability_id == CAPABILITY_ID
    assert view.team_id == "team-a"
    assert view.settings == {"allow_javascript": False}
    assert store.seen == [("team-a", CAPABILITY_ID)]


@pytest.mark.asyncio
async def test_read_returns_the_stored_value(_pod_catalog):
    _pod_catalog.append(_entry())
    store = _SettingsStore({"allow_javascript": True})

    view = await capability_service.read_team_capability_settings(
        capability_id=CAPABILITY_ID,
        team_id="team-a",
        deps=_deps(store, _entry()),
    )

    assert view.settings == {"allow_javascript": True}


@pytest.mark.asyncio
async def test_read_rejects_an_unknown_capability(_pod_catalog):
    from control_plane_backend.capabilities.enablement import CapabilityNotFound

    store = _SettingsStore(None)

    with pytest.raises(CapabilityNotFound):
        await capability_service.read_team_capability_settings(
            capability_id="does_not_exist",
            team_id="team-a",
            deps=_deps(store, _entry()),
        )


# --- authorization: two surfaces, two different gates ---


def _user():
    from fred_core import KeycloakUser

    return KeycloakUser(uid="u-1", username="u", roles=[], email="u@example.com")


@pytest.mark.asyncio
async def test_member_route_gates_on_team_agent_access(monkeypatch):
    """A member reads their own team's posture — not an administrative right."""

    from unittest.mock import AsyncMock

    from control_plane_backend.capabilities import api as capability_api
    from control_plane_backend.teams.schemas import TeamPermission

    access = AsyncMock(return_value="team-a")
    monkeypatch.setattr(capability_api, "require_team_access", access)
    read = AsyncMock(return_value="view")
    monkeypatch.setattr(capability_service, "read_team_capability_settings", read)

    result = await capability_api.get_team_capability_settings(
        "team-a", CAPABILITY_ID, SimpleNamespace(team_dependencies=None), _user()
    )

    assert result == "view"
    assert access.await_args is not None
    assert access.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_USE_TEAM_AGENTS
    ]


@pytest.mark.asyncio
async def test_member_route_denies_a_non_member_before_reading(monkeypatch):
    from unittest.mock import AsyncMock

    from control_plane_backend.capabilities import api as capability_api
    from fastapi import HTTPException
    from fred_core.security.models import AuthorizationError, Resource

    monkeypatch.setattr(
        capability_api,
        "require_team_access",
        AsyncMock(side_effect=AuthorizationError("u-1", "read", Resource.TEAM)),
    )
    read = AsyncMock()
    monkeypatch.setattr(capability_service, "read_team_capability_settings", read)

    with pytest.raises(HTTPException):
        await capability_api.get_team_capability_settings(
            "team-b", CAPABILITY_ID, SimpleNamespace(team_dependencies=None), _user()
        )

    assert read.await_count == 0, "a denied caller must not reach the store"


@pytest.mark.asyncio
async def test_admin_route_gates_on_capability_management(monkeypatch):
    from unittest.mock import AsyncMock

    from control_plane_backend.capabilities import api as capability_api
    from fastapi import HTTPException
    from fred_core.security.models import AuthorizationError, Resource

    monkeypatch.setattr(
        capability_service,
        "require_can_manage_capability",
        AsyncMock(side_effect=AuthorizationError("u-1", "manage", Resource.TEAM)),
    )
    read = AsyncMock()
    monkeypatch.setattr(capability_service, "read_team_capability_settings", read)

    with pytest.raises(HTTPException):
        await capability_api.get_admin_team_capability_settings(
            CAPABILITY_ID, "team-a", SimpleNamespace(), _user()
        )

    assert read.await_count == 0


@pytest.mark.asyncio
async def test_admin_read_resolves_personal_route_alias(monkeypatch):
    from unittest.mock import AsyncMock

    from control_plane_backend.capabilities import api as capability_api

    monkeypatch.setattr(
        capability_service, "require_can_manage_capability", _noop_gate()
    )
    read = AsyncMock(return_value="view")
    monkeypatch.setattr(capability_service, "read_team_capability_settings", read)

    result = await capability_api.get_admin_team_capability_settings(
        CAPABILITY_ID, "personal", SimpleNamespace(), _user()
    )

    assert result == "view"
    assert read.await_args.kwargs["team_id"] == "personal-u-1"


# --- reading back what a disabled team kept ---


@pytest.mark.asyncio
async def test_read_still_answers_for_a_disabled_team(_pod_catalog):
    """Disabling keeps the settings row (covered in test_capability_enablement_1980:
    "settings row KEPT"). What matters here is that the READ path still returns it,
    because that is what the re-enable form seeds from — seeding from the declared
    defaults instead would silently erase what the team had.
    """

    _pod_catalog.append(_entry())
    store = _SettingsStore({"allow_javascript": True})

    view = await capability_service.read_team_capability_settings(
        capability_id=CAPABILITY_ID,
        team_id="team-a",
        deps=_deps(store, _entry()),
    )

    assert view.settings == {"allow_javascript": True}


# --- the settings-only write must not touch enablement ---


@pytest.mark.asyncio
async def test_settings_write_never_touches_the_enablement_tuple(
    _pod_catalog, monkeypatch
):
    """The whole point of the separate route.

    Reusing the enable-with-settings PUT to edit an option would write the
    `enabled` tuple, silently promoting a team that merely INHERITS a default-on
    capability from "Default" to an explicit "Enabled".
    """

    from control_plane_backend.capabilities import enablement

    _pod_catalog.append(_entry())
    store = _SettingsStore(None)
    monkeypatch.setattr(
        capability_service, "require_can_manage_capability", _noop_gate()
    )

    def _explode(*args, **kwargs):
        raise AssertionError("the settings write must not reach enablement")

    for name in ("enable_capability_for_team", "set_capability_default_on"):
        monkeypatch.setattr(enablement, name, _explode)
        monkeypatch.setattr(capability_service, name, _explode, raising=False)

    view = await capability_service.write_team_capability_settings(
        user=_user(),
        capability_id=CAPABILITY_ID,
        team_id="team-a",
        settings={"allow_javascript": True},
        deps=_deps(store, _entry()),
    )

    assert view.settings == {"allow_javascript": True}
    assert store.upserts == [
        ("team-a", CAPABILITY_ID, {"allow_javascript": True}, "u-1")
    ]


@pytest.mark.asyncio
async def test_settings_write_rejects_an_undeclared_key(_pod_catalog, monkeypatch):
    from control_plane_backend.capabilities.enablement import CapabilitySettingsInvalid

    _pod_catalog.append(_entry())
    store = _SettingsStore(None)
    monkeypatch.setattr(
        capability_service, "require_can_manage_capability", _noop_gate()
    )

    with pytest.raises(CapabilitySettingsInvalid):
        await capability_service.write_team_capability_settings(
            user=_user(),
            capability_id=CAPABILITY_ID,
            team_id="team-a",
            settings={"allow_javascript": True, "smuggled": "x"},
            deps=_deps(store, _entry()),
        )

    assert store.upserts == [], "an invalid payload must write nothing"


# --- the bulk read behind the per-row dot ---


@pytest.mark.asyncio
async def test_settings_map_returns_one_entry_per_team_with_a_row(_pod_catalog):
    _pod_catalog.append(_entry())
    store = _SettingsStore(
        None,
        by_team={
            "team-a": {"allow_javascript": True},
            "team-b": {"allow_javascript": False},
            # A key an older manifest declared: dropped, like the single read.
            "team-c": {"allow_javascript": True, "retired": "x"},
        },
    )

    result = await capability_service.read_capability_team_settings_map(
        capability_id=CAPABILITY_ID, deps=_deps(store, _entry())
    )

    assert result.capability_id == CAPABILITY_ID
    assert result.by_team == {
        "team-a": {"allow_javascript": True},
        "team-b": {"allow_javascript": False},
        "team-c": {"allow_javascript": True},
    }


@pytest.mark.asyncio
async def test_settings_map_omits_teams_with_no_row(_pod_catalog):
    """Absent, not defaulted: otherwise the response carries a row per team in
    the organization, and the caller already holds team_settings_fields."""

    _pod_catalog.append(_entry())
    store = _SettingsStore(None, by_team={})

    result = await capability_service.read_capability_team_settings_map(
        capability_id=CAPABILITY_ID, deps=_deps(store, _entry())
    )

    assert result.by_team == {}


def _noop_gate():
    from unittest.mock import AsyncMock

    return AsyncMock(return_value=None)


# --- personal spaces share ONE record ---
#
# Personal access is granted as a class: a single org-level tuple covering
# every personal space. Its options follow the same rule — one platform-wide
# decision, never a per-user one.


@pytest.mark.asyncio
async def test_a_personal_space_reads_the_shared_class_record(_pod_catalog):
    _pod_catalog.append(_entry())
    store = _SettingsStore({"allow_javascript": True})

    view = await capability_service.read_team_capability_settings(
        capability_id=CAPABILITY_ID,
        team_id="personal-alice",
        deps=_deps(store, _entry()),
    )

    assert store.seen == [(PERSONAL_SCOPE_SETTINGS_ID, CAPABILITY_ID)]
    assert view.team_id == PERSONAL_SCOPE_SETTINGS_ID
    assert view.settings == {"allow_javascript": True}


@pytest.mark.asyncio
async def test_two_personal_spaces_cannot_diverge(_pod_catalog):
    """The read every personal space makes is byte-for-byte the same one."""

    _pod_catalog.append(_entry())
    store = _SettingsStore({"allow_javascript": True})

    for uid in ("personal-alice", "personal-bob"):
        view = await capability_service.read_team_capability_settings(
            capability_id=CAPABILITY_ID,
            team_id=uid,
            deps=_deps(store, _entry()),
        )
        assert view.settings == {"allow_javascript": True}

    assert store.seen == [(PERSONAL_SCOPE_SETTINGS_ID, CAPABILITY_ID)] * 2


@pytest.mark.asyncio
async def test_a_write_addressed_to_one_personal_space_lands_on_the_class(
    _pod_catalog, monkeypatch
):
    """Enforced in the service, not only in the admin form.

    A write naming a single personal space must not be able to give that one
    user a posture the others do not have.
    """

    _pod_catalog.append(_entry())
    store = _SettingsStore(None)
    monkeypatch.setattr(
        capability_service, "require_can_manage_capability", _noop_gate()
    )

    view = await capability_service.write_team_capability_settings(
        user=_user(),
        capability_id=CAPABILITY_ID,
        team_id="personal-alice",
        settings={"allow_javascript": True},
        deps=_deps(store, _entry()),
    )

    assert store.upserts == [
        (PERSONAL_SCOPE_SETTINGS_ID, CAPABILITY_ID, {"allow_javascript": True}, "u-1")
    ]
    assert view.team_id == PERSONAL_SCOPE_SETTINGS_ID


@pytest.mark.asyncio
async def test_settings_write_resolves_personal_route_alias(_pod_catalog, monkeypatch):
    _pod_catalog.append(_entry())
    store = _SettingsStore(None)
    monkeypatch.setattr(
        capability_service, "require_can_manage_capability", _noop_gate()
    )

    view = await capability_service.write_team_capability_settings(
        user=_user(),
        capability_id=CAPABILITY_ID,
        team_id="personal",
        settings={"allow_javascript": False},
        deps=_deps(store, _entry()),
    )

    assert view.team_id == PERSONAL_SCOPE_SETTINGS_ID
    assert store.upserts[0][0] == PERSONAL_SCOPE_SETTINGS_ID


@pytest.mark.asyncio
async def test_an_ordinary_team_is_untouched_by_the_class_mapping(_pod_catalog):
    """A team id is a Keycloak group id, so it never wears the personal prefix.

    The mapping keys off `is_personal_team_id`, the platform-wide predicate —
    it is not a second, looser rule invented here.
    """

    _pod_catalog.append(_entry())
    store = _SettingsStore(None)

    await capability_service.read_team_capability_settings(
        capability_id=CAPABILITY_ID,
        team_id="7f3c1a92-0b44-4d21-9e88-2c5a7e11b430",
        deps=_deps(store, _entry()),
    )

    assert store.seen == [("7f3c1a92-0b44-4d21-9e88-2c5a7e11b430", CAPABILITY_ID)]
