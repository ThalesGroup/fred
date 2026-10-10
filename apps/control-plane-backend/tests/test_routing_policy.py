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

Covers: the store's upsert/get + version increment and its atomic
recommendation clearing, the service's write-time validation (default usable
and never disabled, exceptions pruned), the authz gate each service function
requests (read=can_read_members+elevated role, write and disable-impact=
can_update_info), the effective-chat-model read with its selectable models,
and the session-prep snapshot resolver.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy import service as routing_policy_service
from control_plane_backend.routing_policy.schemas import (
    DefaultModelNotDisableableError,
    ModelCatalogUnavailableError,
    ModelDisabledForTeamError,
    ProfileNotUsableError,
    RoutingPolicyVersionConflictError,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.service import resolve_effective_chat_model
from control_plane_backend.routing_policy.store import TeamRoutingPolicyStore
from fred_core import AuthorizationError, KeycloakUser, Resource, TeamPermission
from fred_core.common import TeamId
from fred_sdk.contracts.capability.manifest import CapabilityCatalogEntry
from fred_sdk.contracts.context import ModelBinding
from sqlalchemy.ext.asyncio import AsyncEngine
from test_main import _FakeAgentInstanceStore, _FakeRoutingPolicyStore, _make_record

_POD = "runtime-a"
_POD_URL = "http://pod-a"
# Captured before the autouse fixture stubs it, to test the real helper.
_REAL_UNREACHABLE_TEAM_PODS = routing_policy_service._unreachable_team_pods


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


# ---------------------------------------------------------------------------
# store.py — CRUD + version increment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_when_no_policy_stored(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    assert await store.get(team_id=TeamId("team-1")) is None


async def _upsert(store: TeamRoutingPolicyStore, team_id: str, **kwargs: Any):
    values: dict[str, Any] = {
        "chat_default_profile_id": None,
        "disabled_model_ids": [],
        "reasoning_default_off_model_ids": [],
        "updated_by": "u1",
    }
    values.update(kwargs)
    return await store.upsert(team_id=TeamId(team_id), **values)


@pytest.mark.asyncio
async def test_upsert_then_get_round_trips(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(
        store,
        "team-1",
        chat_default_profile_id="default.chat.mistral",
        disabled_model_ids=["model__b"],
        reasoning_default_off_model_ids=["model__a"],
    )

    stored = await store.get(team_id=TeamId("team-1"))

    assert stored is not None
    assert stored.chat_default_profile_id == "default.chat.mistral"
    assert stored.disabled_model_ids == ("model__b",)
    assert stored.reasoning_default_off_model_ids == ("model__a",)
    assert stored.version == 1


@pytest.mark.asyncio
async def test_second_upsert_increments_version_and_replaces(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(store, "team-1", chat_default_profile_id="p1")
    await _upsert(store, "team-1", chat_default_profile_id="p2", updated_by="u2")

    stored = await store.get(team_id=TeamId("team-1"))

    assert stored is not None
    assert stored.version == 2
    assert stored.chat_default_profile_id == "p2"
    assert stored.updated_by == "u2"


@pytest.mark.asyncio
async def test_upsert_is_scoped_per_team(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(store, "team-1", chat_default_profile_id="p1")

    assert await store.get(team_id=TeamId("team-2")) is None


async def _seed_instance(
    engine: AsyncEngine, agent_instance_id: str, team_id: str, recommended: str | None
) -> None:
    from control_plane_backend.agent_instances.store import (
        AgentInstanceRecord,
        AgentInstanceStore,
    )
    from control_plane_backend.config.models import ManagedAgentTuning

    await AgentInstanceStore(engine).create(
        AgentInstanceRecord(
            agent_instance_id=agent_instance_id,
            team_id=TeamId(team_id),
            template_id="runtime-a:rico",
            source_runtime_id="runtime-a",
            source_agent_id="rico",
            display_name=agent_instance_id,
            description=None,
            enabled=True,
            created_by=None,
            tuning=ManagedAgentTuning(
                role="r", description="d", recommended_chat_profile_id=recommended
            ),
        )
    )


async def _recommendation(engine: AsyncEngine, agent_instance_id: str) -> str | None:
    from control_plane_backend.agent_instances.store import AgentInstanceStore

    record = await AgentInstanceStore(engine).get(agent_instance_id)
    assert record is not None
    return record.tuning.recommended_chat_profile_id


@pytest.mark.asyncio
async def test_upsert_clears_the_team_recommendations_in_the_same_write(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    await _seed_instance(control_plane_sql_engine, "x", "team-1", "chat.b")
    await _seed_instance(control_plane_sql_engine, "z", "team-1", None)
    await _seed_instance(control_plane_sql_engine, "other", "team-2", "chat.b")
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)

    await _upsert(
        store,
        "team-1",
        disabled_model_ids=["model__b"],
        cleared_recommendation_profile_ids=frozenset({"chat.b"}),
    )

    assert await _recommendation(control_plane_sql_engine, "x") is None
    assert await _recommendation(control_plane_sql_engine, "z") is None
    assert await _recommendation(control_plane_sql_engine, "other") == "chat.b"


@pytest.mark.asyncio
async def test_an_agent_save_rechecks_its_recommendation_in_the_write(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    """A model disabled after the service validated the recommendation is
    still refused, by the check inside the agent's own write."""

    from control_plane_backend.agent_instances.store import AgentInstanceStore

    await _seed_instance(control_plane_sql_engine, "x", "team-1", None)
    await _upsert(
        TeamRoutingPolicyStore(engine=control_plane_sql_engine),
        "team-1",
        disabled_model_ids=["model__b"],
    )
    instances = AgentInstanceStore(control_plane_sql_engine)
    record = await instances.get("x")
    assert record is not None

    with pytest.raises(ModelDisabledForTeamError):
        await instances.update(
            "x",
            TeamId("team-1"),
            tuning=record.tuning.model_copy(
                update={"recommended_chat_profile_id": "chat.b"}
            ),
            recommended_capability_id="model__b",
        )
    assert await _recommendation(control_plane_sql_engine, "x") is None

    with pytest.raises(ModelDisabledForTeamError):
        await _seed_instance_checked(control_plane_sql_engine, "y", "chat.b")
    assert await instances.get("y") is None


async def _seed_instance_checked(
    engine: AsyncEngine, agent_instance_id: str, recommended: str
) -> None:
    from control_plane_backend.agent_instances.store import (
        AgentInstanceRecord,
        AgentInstanceStore,
    )
    from control_plane_backend.config.models import ManagedAgentTuning

    await AgentInstanceStore(engine).create(
        AgentInstanceRecord(
            agent_instance_id=agent_instance_id,
            team_id=TeamId("team-1"),
            template_id="runtime-a:rico",
            source_runtime_id="runtime-a",
            source_agent_id="rico",
            display_name=agent_instance_id,
            description=None,
            enabled=True,
            created_by=None,
            tuning=ManagedAgentTuning(
                role="r", description="d", recommended_chat_profile_id=recommended
            ),
        ),
        recommended_capability_id="model__b",
    )


@pytest.mark.asyncio
async def test_an_unrelated_agent_save_never_resurrects_a_cleared_recommendation(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    """The agent form loaded "chat.b", a disable cleared it, then the form
    saved a prompt edit: the stored (cleared) value wins."""

    from control_plane_backend.agent_instances.store import AgentInstanceStore

    await _seed_instance(control_plane_sql_engine, "x", "team-1", "chat.b")
    instances = AgentInstanceStore(control_plane_sql_engine)
    loaded = await instances.get("x")
    assert loaded is not None
    await _upsert(
        TeamRoutingPolicyStore(engine=control_plane_sql_engine),
        "team-1",
        disabled_model_ids=["model__b"],
        cleared_recommendation_profile_ids=frozenset({"chat.b"}),
    )

    await instances.update(
        "x",
        TeamId("team-1"),
        tuning=loaded.tuning.model_copy(update={"role": "edited"}),
        keep_stored_recommendation=True,
    )

    saved = await instances.get("x")
    assert saved is not None
    assert saved.tuning.role == "edited"
    assert saved.tuning.recommended_chat_profile_id is None


@pytest.mark.asyncio
async def test_upsert_refuses_a_stale_expected_version(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(store, "team-1", expected_version=0)
    with pytest.raises(RoutingPolicyVersionConflictError) as exc_info:
        await _upsert(store, "team-1", disabled_model_ids=["m"], expected_version=0)
    assert (exc_info.value.expected, exc_info.value.actual) == (0, 1)
    stored = await _upsert(
        store, "team-1", disabled_model_ids=["m"], expected_version=1
    )
    assert stored.version == 2


@pytest.mark.asyncio
async def test_a_failed_clear_rolls_the_policy_write_back(
    control_plane_sql_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.routing_policy import store as store_module

    await _seed_instance(control_plane_sql_engine, "x", "team-1", "chat.b")
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(store, "team-1", chat_default_profile_id="chat.a")

    async def _boom(*args: Any, **kwargs: Any) -> list[str]:
        raise RuntimeError("clear failed")

    monkeypatch.setattr(store_module, "clear_recommended_chat_profiles", _boom)
    with pytest.raises(RuntimeError):
        await _upsert(
            store,
            "team-1",
            chat_default_profile_id="chat.a",
            disabled_model_ids=["model__b"],
            cleared_recommendation_profile_ids=frozenset({"chat.b"}),
        )

    stored = await store.get(team_id=TeamId("team-1"))
    assert stored is not None
    assert stored.version == 1
    assert stored.disabled_model_ids == ()
    assert await _recommendation(control_plane_sql_engine, "x") == "chat.b"


@pytest.mark.asyncio
async def test_model_revocation_prunes_exceptions_and_clears_recommendations(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    await _seed_instance(control_plane_sql_engine, "x", "team-1", "chat.b")
    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(
        store,
        "team-1",
        disabled_model_ids=["model__b", "model__c"],
        reasoning_default_off_model_ids=["model__b"],
    )

    assert await store.list_team_ids_referencing_model("model__b") == ["team-1"]
    cleared = await store.apply_model_revocation(
        team_id=TeamId("team-1"),
        capability_id="model__b",
        recommendation_profile_ids=frozenset({"chat.b"}),
    )

    assert cleared == ["x"]
    stored = await store.get(team_id=TeamId("team-1"))
    assert stored is not None
    assert stored.disabled_model_ids == ("model__c",)
    assert stored.reasoning_default_off_model_ids == ()
    assert stored.version == 1
    assert await store.list_team_ids_referencing_model("model__b") == []


@pytest.mark.asyncio
async def test_model_revocation_clears_a_team_default_naming_the_model(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    """A revoked stored default is cleared, so the pod default takes over and
    turns keep working; a default on another model is kept."""

    store = TeamRoutingPolicyStore(engine=control_plane_sql_engine)
    await _upsert(store, "team-1", chat_default_profile_id="chat.b")
    await _upsert(store, "team-2", chat_default_profile_id="chat.c")

    assert await store.list_team_ids_referencing_model(
        "model__b", frozenset({"chat.b"})
    ) == ["team-1"]
    await store.apply_model_revocation(
        team_id=TeamId("team-1"),
        capability_id="model__b",
        recommendation_profile_ids=frozenset({"chat.b"}),
    )
    await store.apply_model_revocation(
        team_id=TeamId("team-2"),
        capability_id="model__b",
        recommendation_profile_ids=frozenset({"chat.b"}),
    )

    team_1 = await store.get(team_id=TeamId("team-1"))
    team_2 = await store.get(team_id=TeamId("team-2"))
    assert team_1 is not None and team_1.chat_default_profile_id is None
    assert team_2 is not None and team_2.chat_default_profile_id == "chat.c"


# ---------------------------------------------------------------------------
# service.py — write-time validation
# ---------------------------------------------------------------------------


class _FakeStore(_FakeRoutingPolicyStore):
    """`_FakeRoutingPolicyStore` that records the last write."""

    def __init__(self, stored: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(stored, **kwargs)
        self.upserted: dict[str, Any] | None = None

    async def upsert(self, **kwargs: Any):
        self.upserted = kwargs
        return await super().upsert(**kwargs)


class _FakeDeps:
    """Minimal stand-in for ProductServiceDependencies — only the attributes
    routing_policy.service actually reads."""

    def __init__(
        self,
        *,
        store: _FakeStore,
        rebac: Any,
        source_runtime_ids: list[str] | None = None,
        instances: list[Any] | None = None,
        reasoning_enabled_ids: set[str] | None = None,
    ) -> None:
        self._store = store
        self.team_dependencies = type("_TD", (), {"rebac": rebac})()
        records = list(instances or [])
        records.extend(
            _make_record(
                agent_instance_id=f"inst-{rid}", team_id="team-1", source_runtime_id=rid
            )
            for rid in (source_runtime_ids or [])
        )
        self._agent_instance_store = _FakeAgentInstanceStore(records)
        store._instances = self._agent_instance_store
        self._reasoning_enabled_ids = reasoning_enabled_ids or set()
        self.configuration = SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(enabled=True, base_url=_POD_URL, runtime_id=_POD)
                ]
            )
        )

    def get_team_routing_policy_store(self):
        return self._store

    def get_agent_instance_store(self):
        return self._agent_instance_store

    def get_model_reasoning_store(self):
        ids = self._reasoning_enabled_ids

        class _Store:
            async def list_enabled_model_ids(self):
                return set(ids)

        return _Store()


def _deps(
    *,
    store: _FakeStore,
    rebac: Any,
    source_runtime_ids: list[str] | None = None,
    instances: list[Any] | None = None,
    reasoning_enabled_ids: set[str] | None = None,
) -> ProductServiceDependencies:
    """`_FakeDeps` duck-types `ProductServiceDependencies` (only the
    attributes `routing_policy.service` reads) — one acknowledged type: ignore
    here instead of one per call site below."""

    return _FakeDeps(  # type: ignore[return-value]
        store=store,
        rebac=rebac,
        source_runtime_ids=source_runtime_ids,
        instances=instances,
        reasoning_enabled_ids=reasoning_enabled_ids,
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

    async def _no_pod_defaults(deps, source_runtime_ids):
        return []

    # Never reach a real pod; tests needing a pod default override this.
    monkeypatch.setattr(
        routing_policy_service, "_team_pod_default_profiles", _no_pod_defaults
    )

    async def _all_reachable(deps, source_runtime_ids):
        return []

    monkeypatch.setattr(
        routing_policy_service, "_unreachable_team_pods", _all_reachable
    )
    return catalog


class _FakeRebacElevatedCheck:
    """Fake for `_require_elevated_team_role`'s `has_permissions` BatchCheck —
    a distinct interface from the `has_permission` (singular) fakes below,
    which back `_validate_write`'s `can_team_use_capability` checks instead.
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
async def test_write_requires_can_update_info(_stub_team_lookup) -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), UpdateTeamRoutingPolicyRequest(), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_UPDATE_INFO]


def _role_gate(monkeypatch: pytest.MonkeyPatch, held: set[TeamPermission]) -> None:
    """`require_team_access` for a caller holding exactly `held`."""

    async def _gate(user, team_id, team_deps, required_permissions):
        if not set(required_permissions) <= held:
            raise AuthorizationError(
                user_id=user.uid,
                action="update",
                resource=Resource.TEAM,
                message="denied",
            )
        return team_id

    monkeypatch.setattr(routing_policy_service, "require_team_access", _gate)


_EDITOR = {TeamPermission.CAN_READ_MEMEBERS, TeamPermission.CAN_UPDATE_RESOURCES}
_ADMIN = {TeamPermission.CAN_READ_MEMEBERS, TeamPermission.CAN_UPDATE_INFO}


@pytest.mark.asyncio
async def test_team_editor_cannot_write_the_team_models(monkeypatch) -> None:
    _role_gate(monkeypatch, _EDITOR)
    store = _FakeStore()
    with pytest.raises(AuthorizationError):
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            UpdateTeamRoutingPolicyRequest(),
            _deps(store=store, rebac=None),
        )
    assert store.upserted is None


@pytest.mark.asyncio
async def test_team_admin_can_write_the_team_models(monkeypatch) -> None:
    _role_gate(monkeypatch, _ADMIN)
    policy = await routing_policy_service.update_team_routing_policy(
        _user(),
        TeamId("team-1"),
        UpdateTeamRoutingPolicyRequest(),
        _deps(store=_FakeStore(), rebac=None),
    )
    assert policy.version == 1


@pytest.mark.asyncio
async def test_personal_space_owner_can_write_the_team_models(monkeypatch) -> None:
    """No stub: the real `require_team_access` lets the owner of a personal
    space through its system-team bypass, with no ReBAC round trip."""

    from control_plane_backend.teams import service as teams_service

    monkeypatch.setattr(
        routing_policy_service, "require_team_access", teams_service.require_team_access
    )
    deps = _deps(store=_FakeStore(), rebac=None)
    deps.team_dependencies = SimpleNamespace(rebac=None)  # type: ignore[attr-defined]
    policy = await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("personal"), UpdateTeamRoutingPolicyRequest(), deps
    )
    assert policy.team_id == "personal-u1"


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
    assert policy.disabled_model_ids == []
    assert policy.reasoning_default_off_model_ids == []


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
    request = UpdateTeamRoutingPolicyRequest(chat_default_profile_id="chat.openai.gpt5")
    result = await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), request, deps
    )
    assert result.chat_default_profile_id == "chat.openai.gpt5"
    assert fake_store.upserted is not None
    assert fake_store.upserted["updated_by"] == "u1"


@pytest.mark.asyncio
async def test_empty_request_skips_catalog_and_rebac_entirely(monkeypatch) -> None:
    async def _fail(*args, **kwargs):
        raise AssertionError("must not be called for an empty routing policy")

    monkeypatch.setattr(routing_policy_service, "aggregate_capability_catalog", _fail)
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), UpdateTeamRoutingPolicyRequest(), deps
    )


def _usable(monkeypatch: pytest.MonkeyPatch, ids: set[str] | None) -> None:
    async def _fake_usable(rebac, team_id):
        return ids

    monkeypatch.setattr(routing_policy_service, "usable_capability_ids", _fake_usable)


def _pod_defaults(monkeypatch: pytest.MonkeyPatch, defaults: list[tuple[str, str]]):
    async def _fake(deps, source_runtime_ids):
        return defaults

    monkeypatch.setattr(routing_policy_service, "_team_pod_default_profiles", _fake)


@pytest.mark.asyncio
async def test_set_as_default_on_an_enabled_model(monkeypatch) -> None:
    _usable(monkeypatch, None)
    store = _FakeStore({"team-1": {"chat_default_profile_id": "chat.openai.gpt4o"}})
    result = await routing_policy_service.update_team_routing_policy(
        _user(),
        TeamId("team-1"),
        UpdateTeamRoutingPolicyRequest(
            chat_default_profile_id="chat.openai.gpt5",
            disabled_model_ids=["model__openai__gpt-4o"],
        ),
        _deps(store=store, rebac=_FakeRebacAllowAll()),
    )
    assert result.chat_default_profile_id == "chat.openai.gpt5"
    assert result.disabled_model_ids == ["model__openai__gpt-4o"]


@pytest.mark.asyncio
async def test_disabling_the_default_model_is_rejected(monkeypatch) -> None:
    _usable(monkeypatch, None)
    store = _FakeStore()
    with pytest.raises(DefaultModelNotDisableableError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            # A sibling profile of the same model is still that model.
            UpdateTeamRoutingPolicyRequest(
                chat_default_profile_id="chat.openai.gpt5.creative",
                disabled_model_ids=["model__openai__gpt-5"],
            ),
            _deps(store=store, rebac=_FakeRebacAllowAll()),
        )
    assert exc_info.value.capability_ids == ["model__openai__gpt-5"]
    assert store.upserted is None


@pytest.mark.asyncio
async def test_the_effective_pod_default_cannot_be_disabled_either(monkeypatch) -> None:
    """With no stored team default the pod default is shown as Default, and
    the same rule protects it."""

    _usable(monkeypatch, None)
    _pod_defaults(monkeypatch, [("chat.openai.gpt4o", "model__openai__gpt-4o")])
    with pytest.raises(DefaultModelNotDisableableError):
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            UpdateTeamRoutingPolicyRequest(
                disabled_model_ids=["model__openai__gpt-4o"]
            ),
            _deps(store=_FakeStore(), rebac=_FakeRebacAllowAll()),
        )


@pytest.mark.asyncio
async def test_ids_the_team_can_no_longer_use_are_pruned_on_write(monkeypatch) -> None:
    _usable(monkeypatch, {"model__openai__gpt-5", "model__openai__gpt-4o"})
    _pod_defaults(monkeypatch, [])
    result = await routing_policy_service.update_team_routing_policy(
        _user(),
        TeamId("team-1"),
        UpdateTeamRoutingPolicyRequest(
            disabled_model_ids=["model__openai__gpt-4o", "model__revoked"],
            reasoning_default_off_model_ids=["model__openai__gpt-5", "model__gone"],
        ),
        _deps(store=_FakeStore(), rebac=_FakeRebacAllowAll()),
    )
    assert result.disabled_model_ids == ["model__openai__gpt-4o"]
    assert result.reasoning_default_off_model_ids == ["model__openai__gpt-5"]


@pytest.mark.asyncio
async def test_disabling_a_model_clears_its_recommendations_atomically(
    monkeypatch,
) -> None:
    """Agents X and Y recommend the disabled model (via two of its profiles),
    Z follows the team: X and Y lose their recommendation in the same write.
    A model already disabled before this write clears nothing new."""

    _usable(monkeypatch, None)
    _pod_defaults(monkeypatch, [])
    instances = [
        _make_record(agent_instance_id="x", team_id="team-1"),
        _make_record(agent_instance_id="y", team_id="team-1"),
        _make_record(agent_instance_id="z", team_id="team-1"),
    ]
    for record, profile in zip(
        instances, ["chat.openai.gpt5", "chat.openai.gpt5.creative", None]
    ):
        record.tuning = record.tuning.model_copy(
            update={"recommended_chat_profile_id": profile}
        )
    store = _FakeStore({"team-1": {"disabled_model_ids": ["model__openai__gpt-4o"]}})
    await routing_policy_service.update_team_routing_policy(
        _user(),
        TeamId("team-1"),
        UpdateTeamRoutingPolicyRequest(
            disabled_model_ids=["model__openai__gpt-5", "model__openai__gpt-4o"]
        ),
        _deps(store=store, rebac=_FakeRebacAllowAll(), instances=instances),
    )
    assert store.upserted is not None
    assert store.upserted["cleared_recommendation_profile_ids"] == frozenset(
        {"chat.openai.gpt5", "chat.openai.gpt5.creative"}
    )
    assert [r.tuning.recommended_chat_profile_id for r in instances] == [
        None,
        None,
        None,
    ]
    assert sorted(store.cleared) == ["x", "y"]


@pytest.mark.asyncio
async def test_a_write_from_a_stale_read_is_refused(monkeypatch) -> None:
    _usable(monkeypatch, None)
    store = _FakeStore({"team-1": {"chat_default_profile_id": "chat.openai.gpt5"}})
    with pytest.raises(RoutingPolicyVersionConflictError):
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            UpdateTeamRoutingPolicyRequest(
                chat_default_profile_id="chat.openai.gpt4o", expected_version=0
            ),
            _deps(store=store, rebac=_FakeRebacAllowAll()),
        )
    stored = await store.get(team_id="team-1")
    assert stored is not None and stored.chat_default_profile_id == "chat.openai.gpt5"


def _unreachable(monkeypatch: pytest.MonkeyPatch, runtime_ids: list[str]) -> None:
    async def _fake(deps, source_runtime_ids):
        return runtime_ids

    monkeypatch.setattr(routing_policy_service, "_unreachable_team_pods", _fake)


@pytest.mark.asyncio
async def test_disabling_with_no_stored_default_refuses_when_a_pod_is_unreachable(
    monkeypatch,
) -> None:
    """The unreachable pod's default is unknown, so it could be the model
    being disabled: refuse (503) rather than fail open."""

    _usable(monkeypatch, None)
    _unreachable(monkeypatch, ["pod-b"])
    store = _FakeStore()
    with pytest.raises(ModelCatalogUnavailableError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            UpdateTeamRoutingPolicyRequest(
                disabled_model_ids=["model__openai__gpt-4o"]
            ),
            _deps(store=store, rebac=_FakeRebacAllowAll()),
        )
    assert exc_info.value.runtime_ids == ["pod-b"]
    assert store.upserted is None


@pytest.mark.asyncio
async def test_newly_disabling_refuses_when_a_pod_is_unreachable_even_with_a_default(
    monkeypatch,
) -> None:
    """Recommendations naming the unreachable pod's profiles could not be
    cleared, so a newly disabled model is refused too."""

    _usable(monkeypatch, None)
    _unreachable(monkeypatch, ["pod-b"])
    store = _FakeStore()
    with pytest.raises(ModelCatalogUnavailableError):
        await routing_policy_service.update_team_routing_policy(
            _user(),
            TeamId("team-1"),
            UpdateTeamRoutingPolicyRequest(
                chat_default_profile_id="chat.openai.gpt5",
                disabled_model_ids=["model__openai__gpt-4o"],
            ),
            _deps(store=store, rebac=_FakeRebacAllowAll()),
        )
    assert store.upserted is None


@pytest.mark.asyncio
async def test_an_unreachable_pod_does_not_block_writes_that_disable_nothing_new(
    monkeypatch,
) -> None:
    _usable(monkeypatch, None)
    _unreachable(monkeypatch, ["pod-b"])
    store = _FakeStore(
        {
            "team-1": {
                "chat_default_profile_id": "chat.openai.gpt5",
                "disabled_model_ids": ["model__openai__gpt-4o"],
            }
        }
    )
    result = await routing_policy_service.update_team_routing_policy(
        _user(),
        TeamId("team-1"),
        UpdateTeamRoutingPolicyRequest(
            chat_default_profile_id="chat.openai.gpt5",
            disabled_model_ids=["model__openai__gpt-4o"],
            reasoning_default_off_model_ids=["model__openai__gpt-5"],
        ),
        _deps(store=store, rebac=_FakeRebacAllowAll()),
    )
    assert result.reasoning_default_off_model_ids == ["model__openai__gpt-5"]


@pytest.mark.asyncio
async def test_unreachable_team_pods_names_the_pods_whose_catalog_is_missing(
    monkeypatch,
) -> None:
    from control_plane_backend.product import service as product_service

    async def _fake(base_url: str):
        return None if base_url == "http://pod-b" else object()

    monkeypatch.setattr(product_service, "_model_capabilities_for_source", _fake)
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod-a", runtime_id="a"
                    ),
                    SimpleNamespace(
                        enabled=True, base_url="http://pod-b", runtime_id="b"
                    ),
                    SimpleNamespace(
                        enabled=True, base_url="http://pod-c", runtime_id="c"
                    ),
                ]
            )
        )
    )
    assert await _REAL_UNREACHABLE_TEAM_PODS(deps, {"a", "b"}) == ["b"]  # type: ignore[arg-type]
    assert await _REAL_UNREACHABLE_TEAM_PODS(deps, {"a"}) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# service.py — disable-impact read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_impact_lists_only_agents_recommending_the_model() -> None:
    instances = [
        _make_record(agent_instance_id="x", team_id="team-1", display_name="Xavier"),
        _make_record(agent_instance_id="y", team_id="team-1", display_name="Yann"),
        _make_record(agent_instance_id="z", team_id="team-1", display_name="Zoe"),
        _make_record(agent_instance_id="w", team_id="team-1", display_name="Walt"),
    ]
    for record, profile in zip(
        instances,
        ["chat.openai.gpt5.creative", "chat.openai.gpt5", None, "chat.openai.gpt4o"],
    ):
        record.tuning = record.tuning.model_copy(
            update={"recommended_chat_profile_id": profile}
        )
    impact = await routing_policy_service.get_disable_impact(
        _user(),
        TeamId("team-1"),
        "model__openai__gpt-5",
        _deps(store=_FakeStore(), rebac=None, instances=instances),
    )
    assert [(a.agent_instance_id, a.display_name) for a in impact.agents] == [
        ("x", "Xavier"),
        ("y", "Yann"),
    ]


@pytest.mark.asyncio
async def test_disable_impact_query_count_is_constant(
    monkeypatch, _stub_catalog
) -> None:
    """One instance read and one catalog aggregation, whatever the number of
    agents: no per-instance call."""

    calls = {"list_by_team": 0, "catalog": 0}

    async def _counting_catalog(deps):
        calls["catalog"] += 1
        return _stub_catalog

    monkeypatch.setattr(
        routing_policy_service, "aggregate_capability_catalog", _counting_catalog
    )
    instances = []
    for index in range(25):
        record = _make_record(agent_instance_id=f"a{index}", team_id="team-1")
        record.tuning = record.tuning.model_copy(
            update={"recommended_chat_profile_id": "chat.openai.gpt5"}
        )
        instances.append(record)
    deps = _deps(store=_FakeStore(), rebac=None, instances=instances)
    real_list = deps.get_agent_instance_store().list_by_team

    async def _counting_list(team_id):
        calls["list_by_team"] += 1
        return await real_list(team_id)

    deps.get_agent_instance_store().list_by_team = _counting_list  # type: ignore[method-assign]
    impact = await routing_policy_service.get_disable_impact(
        _user(), TeamId("team-1"), "model__openai__gpt-5", deps
    )
    assert len(impact.agents) == 25
    assert calls == {"list_by_team": 1, "catalog": 1}


@pytest.mark.asyncio
async def test_disable_impact_requires_team_admin(monkeypatch) -> None:
    _role_gate(monkeypatch, _EDITOR)
    with pytest.raises(AuthorizationError):
        await routing_policy_service.get_disable_impact(
            _user(), TeamId("team-1"), "model__x", _deps(store=_FakeStore(), rebac=None)
        )
    _role_gate(monkeypatch, _ADMIN)
    impact = await routing_policy_service.get_disable_impact(
        _user(), TeamId("team-1"), "model__x", _deps(store=_FakeStore(), rebac=None)
    )
    assert impact.agents == []


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


@pytest.mark.asyncio
async def test_available_models_carry_display_name_and_reasoning_availability(
    monkeypatch, _stub_catalog
) -> None:
    _usable(monkeypatch, None)
    _stub_catalog["model__openai__gpt-5"] = _stub_catalog[
        "model__openai__gpt-5"
    ].model_copy(update={"model_display_name": "GPT-5"})
    result = await routing_policy_service.list_available_model_profiles(
        _user(),
        TeamId("team-1"),
        _deps(
            store=_FakeStore(),
            rebac=_elevated_rebac(),
            reasoning_enabled_ids={"model__openai__gpt-5"},
        ),
    )
    by_profile = {p.profile_id: p for p in result.profiles}
    assert by_profile["chat.openai.gpt5"].display_name == "GPT-5"
    assert by_profile["chat.openai.gpt5"].reasoning_available is True
    assert by_profile["chat.openai.gpt4o"].reasoning_available is False


@pytest.mark.asyncio
async def test_available_models_name_the_effective_default(monkeypatch) -> None:
    _usable(monkeypatch, None)
    stored = _FakeStore({"team-1": {"chat_default_profile_id": "chat.openai.gpt5"}})
    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), _deps(store=stored, rebac=_elevated_rebac())
    )
    assert result.effective_default_profile_id == "chat.openai.gpt5"

    _pod_defaults(monkeypatch, [("chat.openai.gpt4o", "model__openai__gpt-4o")])
    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), _deps(store=_FakeStore(), rebac=_elevated_rebac())
    )
    assert result.effective_default_profile_id == "chat.openai.gpt4o"

    _pod_defaults(
        monkeypatch,
        [
            ("chat.openai.gpt4o", "model__openai__gpt-4o"),
            ("chat.openai.gpt5", "model__openai__gpt-5"),
        ],
    )
    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), _deps(store=_FakeStore(), rebac=_elevated_rebac())
    )
    assert result.effective_default_profile_id is None


@pytest.mark.asyncio
async def test_a_model_granted_after_the_policy_was_saved_arrives_enabled(
    monkeypatch,
) -> None:
    """No write on grant: the new model is in `available-models`, absent from
    the stored exception lists, so it reads enabled with reasoning on."""

    _usable(monkeypatch, {"model__openai__gpt-5"})
    store = _FakeStore({"team-1": {"chat_default_profile_id": "chat.openai.gpt5"}})
    deps = _deps(
        store=store,
        rebac=_elevated_rebac(),
        reasoning_enabled_ids={"model__openai__gpt-4o"},
    )
    _usable(monkeypatch, {"model__openai__gpt-5", "model__openai__gpt-4o"})
    result = await routing_policy_service.list_available_model_profiles(
        _user(), TeamId("team-1"), deps
    )
    policy = await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    new = next(p for p in result.profiles if p.capability_id == "model__openai__gpt-4o")
    assert new.reasoning_available is True
    assert "model__openai__gpt-4o" not in policy.disabled_model_ids
    assert "model__openai__gpt-4o" not in policy.reasoning_default_off_model_ids
    assert store.upserted is None


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
async def test_snapshot_resolves_none_when_no_policy_stored() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    assert (
        await routing_policy_service.resolve_execution_routing_snapshot(
            TeamId("team-1"), deps
        )
        is None
    )


@pytest.mark.asyncio
async def test_snapshot_resolves_the_stored_default() -> None:
    store = _FakeStore({"team-1": {"chat_default_profile_id": "chat.openai.gpt5"}})
    deps = _deps(store=store, rebac=None)
    assert (
        await routing_policy_service.resolve_execution_routing_snapshot(
            TeamId("team-1"), deps
        )
        == "chat.openai.gpt5"
    )


# ---------------------------------------------------------------------------
# resolve_effective_chat_model (#2387) — the composer's model label.
#
# What these pin down is the thing the old composer got wrong: the model shown
# must be the one the turn ROUTES to, at every precedence level, and must never
# be the reasoning-enabled model that used to be displayed instead.
# ---------------------------------------------------------------------------


class _FakeInstanceForResolution:
    def __init__(
        self,
        *,
        source_agent_id: str,
        source_runtime_id: str = _POD,
        recommended: str | None = None,
    ) -> None:
        self.source_agent_id = source_agent_id
        self.source_runtime_id = source_runtime_id
        self.tuning = SimpleNamespace(recommended_chat_profile_id=recommended)


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

    def get_platform_model_binding_store(self):
        """No platform binding configured — the common case on every deployment
        that has not set one, and the precondition for the profile-valued
        precedence below to be reachable at all."""

        class _Store:
            async def get(self, *, model_capability="chat", session=None):
                return None

        return _Store()


def _resolution_deps(
    *,
    stored_default: str | None = None,
    stored_disabled: list[str] | None = None,
    stored_reasoning_off: list[str] | None = None,
    rebac: Any = None,
    instance: _FakeInstanceForResolution | None = None,
    sources: list[Any] | None = None,
    reasoning_enabled_ids: set[str] | None = None,
) -> ProductServiceDependencies:
    stored: dict[str, Any] = {}
    if stored_default is not None or stored_disabled or stored_reasoning_off:
        stored["team-1"] = {
            "chat_default_profile_id": stored_default,
            "disabled_model_ids": stored_disabled or [],
            "reasoning_default_off_model_ids": stored_reasoning_off or [],
        }
    return _ResolutionDeps(  # type: ignore[return-value]
        store=_FakeStore(stored),
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


def _three_models() -> list[CapabilityCatalogEntry]:
    return [
        _chat_entry("model__a", "chat.a", name="model-a"),
        _chat_entry("model__b", "chat.b", name="model-b"),
        _chat_entry("model__c", "chat.c", name="model-c"),
    ]


@pytest.mark.asyncio
async def test_effective_model_prefers_the_instance_recommendation(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    _stub_pod_catalog(
        monkeypatch, entries=_three_models(), default_chat_profile_id="chat.c"
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.b",
            instance=_FakeInstanceForResolution(
                source_agent_id="rico", recommended="chat.a"
            ),
        ),
    )
    assert result.name == "model-a"
    assert result.choice_locked is False


@pytest.mark.parametrize("why", ["team-disabled", "not-usable", "unknown"])
@pytest.mark.asyncio
async def test_an_invalid_recommendation_falls_back_to_the_team_default(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup, why: str
) -> None:
    """Same validation as the pod: a recommendation of a disabled, revoked or
    unknown model is ignored, and the team default names the model."""

    class _OnlyBUsable:
        async def has_permission(self, *args, **kwargs) -> bool:
            return True

        async def lookup_resources(self, *args, **kwargs):
            return [SimpleNamespace(id="model__b")]

    _stub_pod_catalog(
        monkeypatch, entries=_three_models(), default_chat_profile_id="chat.c"
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.b",
            stored_disabled=["model__a"] if why == "team-disabled" else None,
            rebac=_OnlyBUsable() if why == "not-usable" else None,
            instance=_FakeInstanceForResolution(
                source_agent_id="rico",
                recommended="chat.ghost" if why == "unknown" else "chat.a",
            ),
        ),
    )
    assert result.name == "model-b"


@pytest.mark.asyncio
async def test_selectable_models_exclude_disabled_and_unusable_models(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """A plain member reads the recommended model plus the models the team
    allows: D disabled by the team and C not usable are left out. Models of
    another pod never appear because only the instance's own pod is read."""

    class _NoC:
        async def has_permission(self, *args, **kwargs) -> bool:
            return True

        async def lookup_resources(self, *args, **kwargs):
            return [SimpleNamespace(id=i) for i in ("model__a", "model__b", "model__d")]

    _stub_pod_catalog(
        monkeypatch,
        entries=[*_three_models(), _chat_entry("model__d", "chat.d", name="model-d")],
        default_chat_profile_id="chat.a",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_disabled=["model__d"],
            stored_reasoning_off=["model__b"],
            rebac=_NoC(),
            reasoning_enabled_ids={"model__a", "model__b"},
        ),
    )
    assert result.name == "model-a"
    assert [
        (m.profile_id, m.reasoning_enabled, m.reasoning_default_on)
        for m in result.selectable_models
    ] == [("chat.a", True, True), ("chat.b", True, False)]


@pytest.mark.asyncio
async def test_selectable_models_offer_one_row_per_model_keyed_by_the_resolved_profile(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    gpt5 = _model_entry(
        "model__openai__gpt-5", ["chat.gpt5", "chat.gpt5.creative"]
    ).model_copy(update={"name": "gpt-5"})
    _stub_pod_catalog(monkeypatch, entries=[gpt5], default_chat_profile_id="chat.gpt5")
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(stored_default="chat.gpt5.creative"),
    )
    assert [m.profile_id for m in result.selectable_models] == ["chat.gpt5.creative"]


@pytest.mark.asyncio
async def test_the_choice_is_locked_by_a_pod_per_agent_override(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    _stub_pod_catalog(
        monkeypatch,
        entries=_three_models(),
        default_chat_profile_id="chat.a",
        agent_chat_profile_overrides={"rico": "chat.c"},
    )
    result = await resolve_effective_chat_model(
        _user(), TeamId("team-1"), "inst-1", _resolution_deps()
    )
    assert result.name == "model-c"
    assert result.choice_locked is True
    assert result.selectable_models == []


@pytest.mark.asyncio
async def test_a_newly_granted_model_is_selectable_with_reasoning_on_by_default(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """Exceptions storage: a model granted after the policy was saved needs
    no team write to arrive enabled, reasoning on by default."""

    _stub_pod_catalog(
        monkeypatch, entries=_three_models(), default_chat_profile_id="chat.a"
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.a",
            stored_disabled=["model__b"],
            reasoning_enabled_ids={"model__c"},
        ),
    )
    new_model = next(
        m for m in result.selectable_models if m.capability_id == "model__c"
    )
    assert new_model.reasoning_enabled is True
    assert new_model.reasoning_default_on is True


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
        _resolution_deps(stored_default="chat.team"),
    )
    # The team default names chat.team/gpt-4.1; the pod's static override
    # wins, so gpt-4o is what answers and what the composer must say.
    assert result.name == "gpt-4o"
    assert result.capability_id == "model__openai__gpt-4o"


@pytest.mark.asyncio
async def test_effective_model_names_the_entry_owning_the_winning_profile(
    monkeypatch: pytest.MonkeyPatch, _stub_team_lookup
) -> None:
    """Pins the "no control-plane change needed" decision: given pod entries the
    pod has ALREADY split (same wire `name`, distinct capability ids because its
    profiles declare `model_id`), this resolution takes the label and the
    reasoning flag from the entry owning the winning profile. It does not cover
    the pod-side merge, which is a runtime concern."""

    _stub_pod_catalog(
        monkeypatch,
        entries=[
            _chat_entry(
                "model__openai__mistral-small",
                "chat.gw.small",
                name="mistral",
                display_name="Mistral Small 4",
            ),
            _chat_entry(
                "model__openai__mistral-medium",
                "chat.gw.medium",
                name="mistral",
                display_name="Mistral Medium 3.1",
            ),
        ],
        default_chat_profile_id="chat.gw.small",
    )
    result = await resolve_effective_chat_model(
        _user(),
        TeamId("team-1"),
        "inst-1",
        _resolution_deps(
            stored_default="chat.gw.medium",
            reasoning_enabled_ids={"model__openai__mistral-small"},
        ),
    )
    assert result.display_name == "Mistral Medium 3.1"
    assert result.capability_id == "model__openai__mistral-medium"
    # The sibling's toggle must not surface an inert control on this model.
    assert result.reasoning_enabled is False


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
    assert result.choice_locked is True
    assert result.selectable_models == []


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
