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
Team routing policy (TEAM-05, #2118, `TEAM-ROUTING-POLICY-RFC.md`).

Covers: the store's upsert/get + version increment (§3), the service's
write-time validation (§3.2 duplicate rules, §7.1-§7.2 id-space translation
+ enablement check), the authz gate each service function requests
(§6 — read=can_read_members, write=can_update_resources), and the
session-prep snapshot resolver (§8.2).
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.routing_policy import service as routing_policy_service
from control_plane_backend.routing_policy.schemas import (
    DuplicateOperationRuleError,
    ProfileNotUsableError,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.store import TeamRoutingPolicyStore
from fred_core import KeycloakUser, TeamPermission
from fred_core.common import PostgresStoreConfig, TeamId
from fred_core.sql import create_async_engine_from_config
from fred_sdk.contracts.capability.manifest import CapabilityCatalogEntry
from fred_sdk.contracts.context import TeamOperationRouteRule

from control_plane_backend.product.dependencies import ProductServiceDependencies


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


def _rule(
    rule_id: str, *, operation: str, purpose: str | None, target: str
) -> TeamOperationRouteRule:
    return TeamOperationRouteRule(
        rule_id=rule_id, operation=operation, purpose=purpose, target_profile_id=target
    )


# ---------------------------------------------------------------------------
# store.py — CRUD + version increment
# ---------------------------------------------------------------------------


async def _make_store(tmp_path) -> TeamRoutingPolicyStore:
    from fred_core.models.base import Base as CoreBase

    from control_plane_backend.models.base import Base as ControlPlaneBase

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
    rule = _rule("r1", operation="planning", purpose=None, target="chat.gpt5")
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="default.chat.mistral",
        operation_rules=[rule],
        updated_by="u1",
    )

    stored = await store.get(team_id=TeamId("team-1"))

    assert stored is not None
    assert stored.chat_default_profile_id == "default.chat.mistral"
    assert stored.operation_rules == (rule,)
    assert stored.version == 1


@pytest.mark.asyncio
async def test_second_upsert_increments_version_and_replaces(tmp_path) -> None:
    store = await _make_store(tmp_path)
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="p1",
        operation_rules=[],
        updated_by="u1",
    )
    await store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="p2",
        operation_rules=[],
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
        operation_rules=[],
        updated_by="u1",
    )

    assert await store.get(team_id=TeamId("team-2")) is None


# ---------------------------------------------------------------------------
# service.py — write-time validation (§3.2, §7.1-§7.2)
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        self.upserted: dict[str, Any] | None = None
        self._stored = None

    async def get(self, *, team_id):
        return self._stored

    async def upsert(
        self, *, team_id, chat_default_profile_id, operation_rules, updated_by
    ):
        from control_plane_backend.routing_policy.store import StoredTeamRoutingPolicy

        self.upserted = {
            "team_id": team_id,
            "chat_default_profile_id": chat_default_profile_id,
            "operation_rules": operation_rules,
            "updated_by": updated_by,
        }
        record = StoredTeamRoutingPolicy(
            team_id=team_id,
            version=1,
            chat_default_profile_id=chat_default_profile_id,
            operation_rules=tuple(operation_rules),
            updated_by=updated_by,
            updated_at=None,
        )
        self._stored = record
        return record


class _FakeDeps:
    """Minimal stand-in for ProductServiceDependencies — only the attributes
    routing_policy.service actually reads."""

    def __init__(self, *, store: _FakeStore, rebac: Any) -> None:
        self._store = store
        self.team_dependencies = type("_TD", (), {"rebac": rebac})()

    def get_team_routing_policy_store(self):
        return self._store


def _deps(*, store: _FakeStore, rebac: Any) -> ProductServiceDependencies:
    """`_FakeDeps` duck-types `ProductServiceDependencies` (only the two
    attributes `routing_policy.service` reads) — one acknowledged type: ignore
    here instead of one per call site below."""

    return _FakeDeps(store=store, rebac=rebac)  # type: ignore[return-value]


def _model_entry(capability_id: str, profile_ids: list[str]) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=capability_id,
        version="1",
        name=capability_id,
        description=capability_id,
        icon="neurology",
        kind="model",
        model_profile_ids=tuple(profile_ids),
    )


@pytest.fixture(autouse=True)
def _stub_team_lookup(monkeypatch: pytest.MonkeyPatch):
    """Every service test exercises validation/store logic, not
    `teams.service.get_team_by_id` itself (covered by teams' own suite) — stub
    it to a no-op that records the requested permission, so assertions can
    confirm §6's read/write gate without a real team+rebac round trip."""

    calls: list[list[TeamPermission]] = []

    async def _fake_get_team_by_id(user, team_id, team_deps, required_permissions):
        calls.append(required_permissions)
        return None

    monkeypatch.setattr(routing_policy_service, "get_team_by_id", _fake_get_team_by_id)
    return calls


@pytest.fixture(autouse=True)
def _stub_catalog(monkeypatch: pytest.MonkeyPatch):
    """Stub the aggregated model catalog so validation tests control exactly
    which profile_ids/capability ids exist, without a real runtime pod fetch."""

    catalog = {
        "model__openai__gpt-5": _model_entry(
            "model__openai__gpt-5", ["chat.openai.gpt5", "chat.openai.gpt5.creative"]
        ),
        "model__openai__gpt-4o": _model_entry(
            "model__openai__gpt-4o", ["chat.openai.gpt4o"]
        ),
    }

    async def _fake_aggregate(deps):
        return catalog

    monkeypatch.setattr(
        routing_policy_service, "aggregate_capability_catalog", _fake_aggregate
    )
    return catalog


@pytest.mark.asyncio
async def test_write_requires_can_update_resources(_stub_team_lookup) -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.update_team_routing_policy(
        _user(), TeamId("team-1"), UpdateTeamRoutingPolicyRequest(), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_UPDATE_RESOURCES]


@pytest.mark.asyncio
async def test_read_requires_can_read_members(_stub_team_lookup) -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    assert _stub_team_lookup[-1] == [TeamPermission.CAN_READ_MEMEBERS]


@pytest.mark.asyncio
async def test_get_with_no_stored_policy_returns_empty_version_zero() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    policy = await routing_policy_service.get_team_routing_policy(
        _user(), TeamId("team-1"), deps
    )
    assert policy.version == 0
    assert policy.chat_default_profile_id is None
    assert policy.operation_rules == []


@pytest.mark.asyncio
async def test_duplicate_rule_id_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    request = UpdateTeamRoutingPolicyRequest(
        operation_rules=[
            _rule(
                "same", operation="planning", purpose=None, target="chat.openai.gpt5"
            ),
            _rule(
                "same", operation="routing", purpose=None, target="chat.openai.gpt4o"
            ),
        ]
    )
    with pytest.raises(DuplicateOperationRuleError):
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )


@pytest.mark.asyncio
async def test_duplicate_operation_purpose_pair_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    request = UpdateTeamRoutingPolicyRequest(
        operation_rules=[
            _rule("r1", operation="planning", purpose="gap", target="chat.openai.gpt5"),
            _rule(
                "r2", operation="planning", purpose="gap", target="chat.openai.gpt4o"
            ),
        ]
    )
    with pytest.raises(DuplicateOperationRuleError):
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )


@pytest.mark.asyncio
async def test_unknown_profile_id_rejected() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    request = UpdateTeamRoutingPolicyRequest(chat_default_profile_id="ghost.profile")
    with pytest.raises(UnknownProfileError) as exc_info:
        await routing_policy_service.update_team_routing_policy(
            _user(), TeamId("team-1"), request, deps
        )
    assert exc_info.value.profile_ids == ["ghost.profile"]


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
        operation_rules=[
            _rule("r1", operation="planning", purpose=None, target="chat.openai.gpt4o")
        ],
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
        operation_rules=[
            _rule(
                "r1",
                operation="planning",
                purpose=None,
                target="chat.openai.gpt5.creative",
            )
        ],
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
# service.py — resolve_execution_routing_snapshot (§8.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_resolves_none_and_empty_when_no_policy_stored() -> None:
    deps = _deps(store=_FakeStore(), rebac=None)
    default_id, rules = await routing_policy_service.resolve_execution_routing_snapshot(
        TeamId("team-1"), deps
    )
    assert default_id is None
    assert rules == []


@pytest.mark.asyncio
async def test_snapshot_resolves_stored_policy() -> None:
    fake_store = _FakeStore()
    await fake_store.upsert(
        team_id=TeamId("team-1"),
        chat_default_profile_id="chat.openai.gpt5",
        operation_rules=[
            _rule("r1", operation="planning", purpose=None, target="chat.openai.gpt4o")
        ],
        updated_by="u1",
    )
    deps = _deps(store=fake_store, rebac=None)

    default_id, rules = await routing_policy_service.resolve_execution_routing_snapshot(
        TeamId("team-1"), deps
    )

    assert default_id == "chat.openai.gpt5"
    assert len(rules) == 1
    assert rules[0].rule_id == "r1"
