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

"""
Team routing policy.

Covers: the store's upsert/get + version increment, the service's
write-time validation (id-space translation + enablement check — uniqueness
of the override itself is structural, `agent_profile_overrides` is a
`dict`), the authz gate each service function requests
(read=can_read_members, write=can_update_resources), and the session-prep
snapshot resolver.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy import service as routing_policy_service
from control_plane_backend.routing_policy.schemas import (
    ProfileNotUsableError,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.service import resolve_effective_chat_model
from control_plane_backend.routing_policy.store import TeamRoutingPolicyStore
from fred_core import AuthorizationError, KeycloakUser, TeamPermission
from fred_core.common import PostgresStoreConfig, TeamId
from fred_core.sql import create_async_engine_from_config
from fred_sdk.contracts.capability.manifest import CapabilityCatalogEntry
from fred_sdk.contracts.context import ModelBinding


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


# ---------------------------------------------------------------------------
# store.py — CRUD + version increment
# ---------------------------------------------------------------------------


async def _make_store(tmp_path) -> TeamRoutingPolicyStore:
    from control_plane_backend.models.base import Base as ControlPlaneBase
    from fred_core.models.base import Base as CoreBase

    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "routing_policy.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ControlPlaneBase.metadata.create_all)
    return TeamRoutingPolicyStore(engine=engine)


@pytest.mark.asyncio
async def test_get_returns_none_when_no_policy_stored(tmp_path) -> None:
    store = await _make_store(tmp_path)
    assert await store.get(team_id=TeamId("team-1")) is None


@pytest.mark.asyncio
async def test_upsert_then_get_round_trips(tmp_path) -> None:
    store = await _make_store(tmp_path)
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="default.chat.mistral",
        agent_profile_overrides={"rico": "chat.gpt5"},
        updated_by="u1",
    )

    stored = await store.get(team_id=TeamId("team-1"))

    assert stored is not None
    assert stored.chat_default_profile_id == "default.chat.mistral"
    assert stored.agent_profile_overrides == {"rico": "chat.gpt5"}
    assert stored.version == 1


@pytest.mark.asyncio
async def test_second_upsert_increments_version_and_replaces(tmp_path) -> None:
    store = await _make_store(tmp_path)
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="p1",
        agent_profile_overrides={},
        updated_by="u1",
    )
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="p2",
        agent_profile_overrides={},
        updated_by="u2",
    )

    stored = await store.get(team_id=TeamId("team-1"))

    assert stored is not None
    assert stored.version == 2
    assert stored.chat_default_profile_id == "p2"
    assert stored.updated_by == "u2"


@pytest.mark.asyncio
async def test_upsert_is_scoped_per_team(tmp_path) -> None:
    store = await _make_store(tmp_path)
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="p1",
        agent_profile_overrides={},
        updated_by="u1",
    )

    assert await store.get(team_id=TeamId("team-2")) is None


# ---------------------------------------------------------------------------
# service.py — write-time validation
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        self.upserted: dict[str, Any] | None = None
        self._stored = None

    async def get(self, *, team_id):
        return self._stored

    async def upsert(
        self, *, team_id, chat_default_profile_id, agent_profile_overrides, updated_by
    ):
        from control_plane_backend.routing_policy.store import StoredTeamRoutingPolicy

        self.upserted = {
            "team_id": team_id,
            "chat_default_profile_id": chat_default_profile_id,
            "agent_profile_overrides": agent_profile_overrides,
            "updated_by": updated_by,
        }
        record = StoredTeamRoutingPolicy(
            team_id=team_id,
            version=1,
            chat_default_profile_id=chat_default_profile_id,
            agent_profile_overrides=dict(agent_profile_overrides),
            updated_by=updated_by,
            updated_at=None,
        )
        self._stored = record
        return record


class _FakeAgentInstance:
    def __init__(self, source_runtime_id: str) -> None:
        self.source_runtime_id = source_runtime_id


class _FakeAgentInstanceStore:
    def __init__(self, source_runtime_ids: list[str] | None = None) -> None:
        self._instances = [
            _FakeAgentInstance(rid) for rid in (source_runtime_ids or [])
        ]

    async def list_by_team(self, team_id):
        return self._instances


class _FakeDeps:
    """Minimal stand-in for ProductServiceDependencies — only the attributes
    routing_policy.service actually reads."""

    def __init__(
        self,
        *,
        store: _FakeStore,
        rebac: Any,
        source_runtime_ids: list[str] | None = None,
    ) -> None:
        self._store = store
        self.team_dependencies = type("_TD", (), {"rebac": rebac})()
        self._agent_instance_store = _FakeAgentInstanceStore(source_runtime_ids)

    def get_team_routing_policy_store(self):
        return self._store

    def get_agent_instance_store(self):
        return self._agent_instance_store


def _deps(
    *, store: _FakeStore, rebac: Any, source_runtime_ids: list[str] | None = None
) -> ProductServiceDependencies:
    """`_FakeDeps` duck-types `ProductServiceDependencies` (only the
    attributes `routing_policy.service` reads) — one acknowledged type: ignore
    here instead of one per call site below."""

    return _FakeDeps(  # type: ignore[return-value]
        store=store, rebac=rebac, source_runtime_ids=source_runtime_ids
    )


def _model_entry(
    capability_id: str,
    profile_ids: list[str],
    *,
    chat_profile_ids: list[str] | None = None,
) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=capability_id,
        version="1",
        name=capability_id,
        description=capability_id,
        icon="neurology",
        kind="model",
        model_profile_ids=tuple(profile_ids),
        model_chat_profile_ids=tuple(
            profile_ids if chat_profile_ids is None else chat_profile_ids
        ),
    )


@pytest.fixture(autouse=True)
def _stub_team_lookup(monkeypatch: pytest.MonkeyPatch):
    """Every service test exercises validation/store logic, not
    `teams.service.require_team_access` itself (covered by teams' own suite) —
    stub it to a no-op that records the requested permission, so assertions
    can confirm the read/write gate without a real team+rebac round trip."""

    calls: list[list[TeamPermission]] = []

    async def _fake_require_team_access(user, team_id, team_deps, required_permissions):
        calls.append(required_permissions)
        return team_id

    monkeypatch.setattr(
        routing_policy_service, "require_team_access", _fake_require_team_access
    )
    return calls


@pytest.fixture(autouse=True)
def _stub_catalog(monkeypatch: pytest.MonkeyPatch):
    """Stub the aggregated model catalog so validation tests control exactly
    which profile_ids/capability ids exist, without a real runtime pod fetch.

    Also stubs `universally_available_chat_model_profile_ids` to the full set
    of chat profile ids in `catalog` by default — i.e. "every pod agrees", so every
    existing test keeps its original no-drift baseline. Tests that need to
    simulate a pod-coverage gap (MDL#2) override this stub directly.
    """

    catalog = {
        "model__openai__gpt-5": _model_entry(
            "model__openai__gpt-5", ["chat.openai.gpt5", "chat.openai.gpt5.creative"]
        ),
        "model__openai__gpt-4o": _model_entry(
            "model__openai__gpt-4o", ["chat.openai.gpt4o"]
        ),
        "model__openai__text-embedding-3-small": _model_entry(
            "model__openai__text-embedding-3-small",
            ["embedding.openai.small"],
            chat_profile_ids=[],
        ),
    }
    universal = frozenset(
        profile_id
        for entry in catalog.values()
        for profile_id in entry.model_chat_profile_ids
    )

    async def _fake_aggregate(deps):
        return catalog

    async def _fake_universal(deps, *, source_runtime_ids=None):
        return universal

    monkeypatch.setattr(
        routing_policy_service, "aggregate_capability_catalog", _fake_aggregate
    )
    monkeypatch.setattr(
        routing_policy_service,
        "universally_available_chat_model_profile_ids",
        _fake_universal,
    )
    return catalog


class _FakeRebacElevatedCheck:
    """Fake for `_require_elevated_team_role`'s `has_permissions` BatchCheck —
    a distinct interface from the `has_permission` (singular) fakes below,
    which back `_validate_write`'s `can_use_capability` checks instead.
    `allowed` is the fixed `[can_update_info, can_update_resources,
    can_run_evaluations]` result, in `_ELEVATED_TEAM_ROLE_PERMISSIONS` order.
    """

    def __init__(self, allowed: list[bool]) -> None:
        self.allowed = allowed
        self.calls = 0

    async def has_permissions(self, subject, permissions, resource, **kwargs):
        self.calls += 1
        return self.allowed


def _elevated_rebac(
    *, admin=True, editor=False, analyst=False
) -> _FakeRebacElevatedCheck:
    return _FakeRebacElevatedCheck([admin, editor, analyst])


@pytest.mark.asyncio
async def test_write_requires_can_update_resources(_stub_team_lookup) -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), UpdateTeamRoutingPolicyRequest(), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_UPDATE_RESOURCES]


@pytest.mark.asyncio
async def test_read_requires_can_read_members(_stub_team_lookup) -> None:
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())
    await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_READ_MEMEBERS]


@pytest.mark.asyncio
async def test_get_with_no_stored_policy_returns_empty_version_zero() -> None:
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())
    policy = await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    assert policy.version == 0
    assert policy.chat_default_profile_id is None
    assert policy.agent_profile_overrides == {}


@pytest.mark.asyncio
async def test_unknown_profile_id_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    request = UpdateTeamRoutingPolicyRequest(chat_default_profile_id="ghost.profile")
    with pytest.raises(UnknownProfileError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["ghost.profile"]


@pytest.mark.asyncio
async def test_override_targeting_unknown_profile_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    request = UpdateTeamRoutingPolicyRequest(
        agent_profile_overrides={"rico": "ghost.profile"}
    )
    with pytest.raises(UnknownProfileError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["ghost.profile"]


@pytest.mark.asyncio
async def test_non_chat_profile_rejected_even_when_the_model_is_known() -> None:
    deps = _deps(store=_FakeStore(), rebac=_FakeRebacAllowAll())
    request = UpdateTeamRoutingPolicyRequest(
        chat_default_profile_id="embedding.openai.small"
    )
    with pytest.raises(UnknownProfileError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["embedding.openai.small"]


@pytest.mark.asyncio
async def test_profile_missing_from_some_pods_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MDL#2 regression: a profile can be in the aggregated (unioned) catalog
    — some pod advertises it — while being absent from another pod's own
    `models_catalog.yaml`. Writing a policy that references it must be
    rejected at write time, not left to fail at runtime on whichever pod
    lacks it (`TeamRoutingProfileDriftError`)."""

    async def _fake_universal(deps, *, source_runtime_ids=None):
        return frozenset({"chat.openai.gpt4o"})  # chat.openai.gpt5 missing on some pod

    monkeypatch.setattr(
        routing_policy_service,
        "universally_available_chat_model_profile_ids",
        _fake_universal,
    )
    deps = _deps(store=_FakeStore(), rebac=_FakeRebacAllowAll())
    request = UpdateTeamRoutingPolicyRequest(chat_default_profile_id="chat.openai.gpt5")
    with pytest.raises(UnknownProfileError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["chat.openai.gpt5"]


class _FakeRebacDenyAll:
    async def has_permission(self, *args, **kwargs) -> bool:
        return False


class _FakeRebacAllowAll:
    async def has_permission(self, *args, **kwargs) -> bool:
        return True


@pytest.mark.asyncio
async def test_not_usable_profile_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=_FakeRebacDenyAll())
    request = UpdateTeamRoutingPolicyRequest(chat_default_profile_id="chat.openai.gpt5")
    with pytest.raises(ProfileNotUsableError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["chat.openai.gpt5"]


@pytest.mark.asyncio
async def test_usable_profile_accepted_and_persisted() -> None:
    fake_store = _FakeStore()
    deps = _deps(store=fake_store, rebac=_FakeRebacAllowAll())
    request = UpdateTeamRoutingPolicyRequest(
        chat_default_profile_id="chat.openai.gpt5",
        agent_profile_overrides={"rico": "chat.openai.gpt4o"},
    )
    result = await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), request, deps
    )
    assert result.chat_default_profile_id == "chat.openai.gpt5"
    assert fake_store.upserted is not None
    assert fake_store.upserted["updated_by"] == "u1"


@pytest.mark.asyncio
async def test_sibling_profiles_sharing_capability_only_checked_once() -> None:
    # chat.openai.gpt5 and chat.openai.gpt5.creative share model__openai__gpt-5
    # (see _stub_catalog) — referencing both in one write must not require two
    # separate can_use checks against the same capability id.
    calls = 0

    class _CountingRebac:
        async def has_permission(self, *args, **kwargs) -> bool:
            nonlocal calls
            calls += 1
            return True

    deps = _deps(store=_FakeStore(), rebac=_CountingRebac())
    request = UpdateTeamRoutingPolicyRequest(
        chat_default_profile_id="chat.openai.gpt5",
        agent_profile_overrides={"rico": "chat.openai.gpt5.creative"},
    )
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), request, deps
    )
    assert calls == 1


@pytest.mark.asyncio
async def test_empty_request_skips_catalog_and_rebac_entirely(monkeypatch) -> None:
    async def _fail(*args, **kwargs):
        raise AssertionError("must not be called for an empty routing policy")

    monkeypatch.setattr(routing_policy_service, "aggregate_capability_catalog", _fail)
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), UpdateTeamRoutingPolicyRequest(), deps
    )


# ---------------------------------------------------------------------------
# service.py — list_available_model_profiles (routing-policy picker)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_available_models_requires_can_read_members(
    _stub_team_lookup, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_usable(rebac, team_id):
        return None

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())

    await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_READ_MEMEBERS]


@pytest.mark.asyncio
async def test_available_models_unscoped_when_rebac_disabled(monkeypatch) -> None:
    async def _fake_usable(rebac, team_id):
        return None

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())

    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )

    assert sorted(p.profile_id for p in result.profiles) == [
        "chat.openai.gpt4o",
        "chat.openai.gpt5",
        "chat.openai.gpt5.creative",
    ]


@pytest.mark.asyncio
async def test_available_models_filtered_by_usable_capability_ids(monkeypatch) -> None:
    async def _fake_usable(rebac, team_id):
        return {"model__openai__gpt-4o"}

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())

    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )

    assert [p.profile_id for p in result.profiles] == ["chat.openai.gpt4o"]


@pytest.mark.asyncio
async def test_available_models_empty_when_no_capability_usable(monkeypatch) -> None:
    async def _fake_usable(rebac, team_id):
        return set()

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())

    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )

    assert result.profiles == []


@pytest.mark.asyncio
async def test_available_models_excludes_profile_missing_from_some_pods(
    monkeypatch,
) -> None:
    """MDL#2: the picker must never offer a choice the write-path would then
    reject — both read from `universally_available_chat_model_profile_ids`."""

    async def _fake_usable(rebac, team_id):
        return None

    async def _fake_universal(deps, *, source_runtime_ids=None):
        return frozenset({"chat.openai.gpt4o"})

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    monkeypatch.setattr(
        routing_policy_service,
        "universally_available_chat_model_profile_ids",
        _fake_universal,
    )
    deps = _deps(store=_FakeStore(), rebac=_elevated_rebac())

    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )

    assert [p.profile_id for p in result.profiles] == ["chat.openai.gpt4o"]


# ---------------------------------------------------------------------------
# service.py — _require_elevated_team_role read gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_denied_for_plain_team_member() -> None:
    deps = _deps(
        store=_FakeStore(), rebac=_FakeRebacElevatedCheck([False, False, False])
    )
    with pytest.raises(AuthorizationError):
        await routing_policy_service.get_team_routing_policy(
            _user(), TeamId("team-1"), deps
        )


@pytest.mark.parametrize(
    "allowed", [[True, False, False], [False, True, False], [False, False, True]]
)
@pytest.mark.asyncio
async def test_read_allowed_for_any_elevated_role(allowed: list[bool]) -> None:
    deps = _deps(store=_FakeStore(), rebac=_FakeRebacElevatedCheck(allowed))
    policy = await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    assert policy.version == 0


@pytest.mark.asyncio
async def test_available_models_denied_for_plain_team_member(monkeypatch) -> None:
    async def _fake_usable(rebac, team_id):
        return None

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)
    deps = _deps(
        store=_FakeStore(), rebac=_FakeRebacElevatedCheck([False, False, False])
    )
    with pytest.raises(AuthorizationError):
        await routing_policy_service.list_available_model_profiles(
            _user(), TeamId("team-1"), deps
        )


@pytest.mark.asyncio
async def test_elevated_role_check_skipped_for_personal_space() -> None:
    # A personal-space owner holds team_editor unconditionally and must never
    # be denied here even if a real ReBAC round trip would say otherwise
    # (e.g. a not-yet-self-healed tuple) — `is_personal_team_id` short-
    # circuits before `has_permissions` is ever called.
    rebac = _FakeRebacElevatedCheck([False, False, False])
    deps = _deps(store=_FakeStore(), rebac=rebac)
    policy = await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("personal-u1"), deps
    )
    assert policy.version == 0
    assert rebac.calls == 0


# ---------------------------------------------------------------------------
# service.py — resolve_execution_routing_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_resolves_none_and_empty_when_no_policy_stored() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    (
        default_id,
        overrides,
    ) = await routing_policy_service.resolve_execution_routing_snapshot(
        TeamId("team-1"), deps
    )
    assert default_id is None
    assert overrides == {}


@pytest.mark.asyncio
async def test_snapshot_resolves_stored_policy() -> None:
    fake_store = _FakeStore()
    await fake_store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="chat.openai.gpt5",
        agent_profile_overrides={"rico": "chat.openai.gpt4o"},
        updated_by="u1",
    )
    deps = _deps(store=fake_store, rebac=None)

    (
        default_id,
        overrides,
    ) = await routing_policy_service.resolve_execution_routing_snapshot(
        TeamId("team-1"), deps
    )

    assert default_id == "chat.openai.gpt5"
    assert overrides == {"rico": "chat.openai.gpt4o"}


# ---------------------------------------------------------------------------
# resolve_effective_chat_model (#2387) — the composer's model label.
#
# What these pin down is the thing the old composer got wrong: the model shown
# must be the one the turn ROUTES to, at every precedence level, and must never
# be the reasoning-enabled model that used to be displayed instead.
# ---------------------------------------------------------------------------

_POD = "runtime-a"
_POD_URL = "http://pod-a"


class _FakeInstanceForResolution:
    def __init__(self, *, source_agent_id: str, source_runtime_id: str = _POD) -> None:
        self.source_agent_id = source_agent_id
        self.source_runtime_id = source_runtime_id


class _FakeRebacUnscoped:
    """ReBAC disabled: `usable_capability_ids` returns `None`, which means
    "unrestricted" — deliberately NOT the same as "nothing usable", the
    distinction `enabled_for_team` has to get right."""

    async def has_permission(self, *args, **kwargs) -> bool:
        return True

    async def lookup_resources(self, *args, **kwargs):
        from fred_core.security.rebac.rebac_engine import RebacDisabledResult

        return RebacDisabledResult()


class _FakeRebacNothingUsable:
    """ReBAC enabled and this team is `can_use`-enabled for no capability."""

    async def has_permission(self, *args, **kwargs) -> bool:
        return False

    async def lookup_resources(self, *args, **kwargs):
        return []


class _ResolutionDeps(_FakeDeps):
    """`_FakeDeps` plus the two reads only the resolution performs: the pinned
    agent instance, and the pod source list it maps `source_runtime_id` through."""

    def __init__(
        self,
        *,
        store: _FakeStore,
        rebac: Any,
        instance: _FakeInstanceForResolution | None,
        sources: list[Any] | None = None,
        reasoning_enabled_ids: set[str] | None = None,
    ) -> None:
        super().__init__(store=store, rebac=rebac)
        self._instance = instance
        self._reasoning_enabled_ids = reasoning_enabled_ids or set()
        self.configuration = SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=sources
                if sources is not None
                else [SimpleNamespace(enabled=True, base_url=_POD_URL, runtime_id=_POD)]
            )
        )

    def get_agent_instance_store(self):  # type: ignore[override]
        """Only `get_for_team` is read by the resolution, so this deliberately
        returns a narrower stand-in than `_FakeDeps`' list-oriented one."""

        instance = self._instance

        class _Store:
            async def get_for_team(self, agent_instance_id, team_id):
                # Mirrors the real store's two-column filter: an instance is
                # only visible through its OWN team. A double that ignored
                # team_id could not catch a cross-team regression.
                if instance is None or team_id != TeamId("team-1"):
                    return None
                return instance

        return _Store()

    def get_model_reasoning_store(self):
        """Only the enabled-model-id list is read by the resolution."""

        ids = self._reasoning_enabled_ids

        class _Store:
            async def list_enabled_model_ids(self):
                return set(ids)

        return _Store()

    def get_platform_model_binding_store(self):
        """No platform binding configured — the common case on every deployment
        that has not set one, and the precondition for the profile-valued
        precedence below to be reachable at all."""

        class _Store:
            async def get(self, *, model_capability="chat"):
                return None

        return _Store()


def _resolution_deps(
    *,
    stored_default: str | None = None,
    stored_overrides: dict[str, str] | None = None,
    rebac: Any = None,
    instance: _FakeInstanceForResolution | None = None,
    sources: list[Any] | None = None,
    reasoning_enabled_ids: set[str] | None = None,
) -> ProductServiceDependencies:
    from control_plane_backend.routing_policy.store import StoredTeamRoutingPolicy

    store = _FakeStore()
    if stored_default is not None or stored_overrides:
        store._stored = StoredTeamRoutingPolicy(
            team_id=TeamId("team-1"),
            version=1,
            chat_default_profile_id=stored_default,
            agent_profile_overrides=dict(stored_overrides or {}),
            updated_by="someone",
            updated_at=None,
        )
    return _ResolutionDeps(  # type: ignore[return-value]
        store=store,
        rebac=rebac if rebac is not None else _FakeRebacUnscoped(),
        instance=instance
        if instance is not None
        else _FakeInstanceForResolution(source_agent_id="rico"),
        sources=sources,
        reasoning_enabled_ids=reasoning_enabled_ids,
    )


def _stub_pod_catalog(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entries: list[CapabilityCatalogEntry],
    default_chat_profile_id: str | None = None,
    agent_chat_profile_overrides: dict[str, str] | None = None,
    unreachable: bool = False,
) -> None:
    from control_plane_backend.product import service as product_service
    from control_plane_backend.product.service import PodModelCatalog

    async def _fake(base_url: str):
        if unreachable:
            return None
        return PodModelCatalog(
            entries=entries,
            default_chat_profile_id=default_chat_profile_id,
            agent_chat_profile_overrides=dict(agent_chat_profile_overrides or {}),
        )

    monkeypatch.setattr(product_service, "_model_capabilities_for_source", _fake)


def _chat_entry(
    capability_id: str,
    profile_id: str,
    *,
    name: str = "gpt-4.1",
    display_name: str | None = None,
) -> CapabilityCatalogEntry:
    entry = _model_entry(capability_id, [profile_id])
    return entry.model_copy(
        update={
            # `name` IS the concrete model name for a kind="model" entry — the
            # field the resolution reads.
            "name": name,
            "model_display_name": display_name,
        }
    )


@pytest.mark.asyncio
async def test_effective_model_falls_back_to_the_pod_default(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """No team policy: the pod default is what actually answers, so it is what
    the composer must name."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[_chat_entry("model__openai__gpt-5.1", "chat.pod", name="gpt-5.1")],
        default_chat_profile_id="chat.pod",
    )
    result = await resolve_effective_chat_model(
        _user(), TeamId("team-1"), "inst-1", _resolution_deps()
    )
    assert result.name == "gpt-5.1"
    assert result.enabled_for_team is True


@pytest.mark.asyncio
async def test_effective_model_prefers_the_team_default_over_the_pod_default(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    _stub_pod_catalog(
        monkeypatch,
        entries=[
            _chat_entry("model__openai__gpt-5.1", "chat.pod", name="gpt-5.1"),
            _chat_entry("model__openai__gpt-4.1", "chat.team", name="gpt-4.1"),
        ],
        default_chat_profile_id="chat.pod",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(stored_default="chat.team"),
    )
    assert result.name == "gpt-4.1"


@pytest.mark.asyncio
async def test_effective_model_prefers_the_team_agent_override(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """The exact case that looked broken in the UI: a per-agent override set,
    and the composer must name IT, not the team default and not the pod's."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[
            _chat_entry("model__openai__gpt-5.1", "chat.pod", name="gpt-5.1"),
            _chat_entry("model__openai__gpt-4.1", "chat.team", name="gpt-4.1"),
            _chat_entry("model__openai__gpt-4o", "chat.rico", name="gpt-4o"),
        ],
        default_chat_profile_id="chat.pod",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.team", stored_overrides={"rico": "chat.rico"}
        ),
    )
    assert result.name == "gpt-4o"


@pytest.mark.asyncio
async def test_effective_model_lets_the_pod_static_override_win(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """The operator's local escape hatch outranks every team level (#2380's
    documented precedence) — the composer must not promise the team's choice."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[
            _chat_entry("model__openai__gpt-4.1", "chat.team", name="gpt-4.1"),
            _chat_entry("model__openai__gpt-4o", "chat.ops", name="gpt-4o"),
        ],
        default_chat_profile_id="chat.team",
        agent_chat_profile_overrides={"rico": "chat.ops"},
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.team", stored_overrides={"rico": "chat.team"}
        ),
    )
    # Both team levels named chat.team/gpt-4.1; the pod's static override wins,
    # so gpt-4o is what answers and what the composer must say.
    assert result.name == "gpt-4o"
    assert result.capability_id == "model__openai__gpt-4o"


@pytest.mark.asyncio
async def test_effective_model_reports_a_model_not_enabled_for_the_team(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """The turn will fail with ModelNotUsableError. The composer names the model
    AND flags it, so the user learns why instead of hitting an opaque error."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[_chat_entry("model__openai__gpt-4.1", "chat.pod")],
        default_chat_profile_id="chat.pod",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(rebac=_FakeRebacNothingUsable()),
    )
    assert result.name == "gpt-4.1"
    assert result.enabled_for_team is False


@pytest.mark.asyncio
async def test_effective_model_is_empty_when_the_pod_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """A pod being down must not break the chat page."""

    _stub_pod_catalog(monkeypatch, entries=[], unreachable=True)
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(stored_default="chat.team"),
    )
    assert result.name is None


@pytest.mark.asyncio
async def test_effective_model_is_empty_when_no_level_declares_anything(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    _stub_pod_catalog(
        monkeypatch, entries=[_chat_entry("model__openai__gpt-4.1", "chat.pod")]
    )
    result = await resolve_effective_chat_model(
        _user(), TeamId("team-1"), "inst-1", _resolution_deps()
    )
    assert result.name is None


@pytest.mark.asyncio
async def test_effective_model_is_empty_when_the_winning_profile_is_unknown_to_the_pod(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """Team-policy drift — the same condition that raises
    TeamRoutingProfileDriftError at turn time. No model can be named, and
    inventing one would be worse than showing none."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[_chat_entry("model__openai__gpt-4.1", "chat.pod")],
        default_chat_profile_id="chat.pod",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(stored_default="chat.ghost"),
    )
    assert result.name is None


@pytest.mark.asyncio
async def test_effective_model_consults_only_the_instance_own_pod(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """An instance is pinned to one pod for its whole life, so another pod's
    catalog has no say in what this agent will run."""

    seen: list[str] = []
    from control_plane_backend.product import service as product_service
    from control_plane_backend.product.service import PodModelCatalog

    async def _fake(base_url: str):
        seen.append(base_url)
        return PodModelCatalog(
            entries=[_chat_entry("model__openai__gpt-4.1", "chat.pod")],
            default_chat_profile_id="chat.pod",
        )

    monkeypatch.setattr(product_service, "_model_capabilities_for_source", _fake)
    deps = _resolution_deps(
        instance=_FakeInstanceForResolution(
            source_agent_id="rico", source_runtime_id="runtime-b"
        ),
        sources=[
            SimpleNamespace(enabled=True, base_url=_POD_URL, runtime_id=_POD),
            SimpleNamespace(
                enabled=True, base_url="http://pod-b", runtime_id="runtime-b"
            ),
        ],
    )
    await resolve_effective_chat_model(_user(), TeamId("team-1"), "inst-1", deps)
    assert seen == ["http://pod-b"]


@pytest.mark.asyncio
async def test_effective_model_platform_binding_outranks_everything(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """An operator binding wins over every profile level, bypasses team
    enablement by design, and needs no pod fetch at all."""

    from control_plane_backend.routing_policy import service as rp_service

    async def _binding(deps):
        return ModelBinding(provider="anthropic", name="claude-sonnet-4-6")

    monkeypatch.setattr(rp_service, "resolve_platform_chat_model_binding", _binding)

    async def _must_not_fetch(base_url: str):
        raise AssertionError("a platform binding must short-circuit the pod fetch")

    from control_plane_backend.product import service as product_service

    monkeypatch.setattr(
        product_service, "_model_capabilities_for_source", _must_not_fetch
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(stored_default="chat.team", rebac=_FakeRebacNothingUsable()),
    )
    assert result.name == "claude-sonnet-4-6"
    assert result.enabled_for_team is True


@pytest.mark.asyncio
async def test_effective_model_reports_reasoning_enabled_for_the_routed_model(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """The composer needs this to decide whether the reasoning toggle is worth
    showing — the platform list alone says nothing about the ROUTED model."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[_chat_entry("model__openai__mistral-small", "chat.small")],
        default_chat_profile_id="chat.small",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(reasoning_enabled_ids={"model__openai__mistral-small"}),
    )
    assert result.reasoning_enabled is True


@pytest.mark.asyncio
async def test_effective_model_reports_reasoning_off_for_a_non_reasoning_model(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """The production bug: reasoning enabled on a DIFFERENT model. Offering the
    toggle here would be offering something `RoutedChatModelFactory` strips."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[_chat_entry("model__openai__mistral-medium", "chat.medium")],
        default_chat_profile_id="chat.medium",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(reasoning_enabled_ids={"model__openai__mistral-small"}),
    )
    assert result.reasoning_enabled is False


@pytest.mark.asyncio
async def test_effective_model_ignores_a_disabled_runtime_source(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """A disabled source is one prepare_execution refuses to prepare against, so
    naming a model from its catalog would promise a turn that then fails."""

    async def _must_not_fetch(base_url: str):
        raise AssertionError("a disabled runtime source must not be contacted")

    from control_plane_backend.product import service as product_service

    monkeypatch.setattr(
        product_service, "_model_capabilities_for_source", _must_not_fetch
    )
    deps = _resolution_deps(
        sources=[SimpleNamespace(enabled=False, base_url=_POD_URL, runtime_id=_POD)]
    )
    result = await resolve_effective_chat_model(
        _user(), TeamId("team-1"), "inst-1", deps
    )
    assert result.name is None


@pytest.mark.asyncio
async def test_effective_model_is_empty_for_an_instance_of_another_team(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """Cross-team read: the instance lookup filters on `(agent_instance_id,
    team_id)`, so an id belonging to another team resolves to nothing — and
    nothing downstream (binding, pod catalog, policy, enablement) is consulted.
    """

    async def _must_not_fetch(base_url: str):
        raise AssertionError("a foreign instance must not reach the pod catalog")

    from control_plane_backend.product import service as product_service

    monkeypatch.setattr(
        product_service, "_model_capabilities_for_source", _must_not_fetch
    )
    result = await resolve_effective_chat_model(
        _user(), TeamId("team-2"), "inst-of-team-1", _resolution_deps()
    )
    assert result.name is None
    assert result.capability_id is None
