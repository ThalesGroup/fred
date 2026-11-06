# SPDX-License-Identifier: Apache-2.0
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fred_pod.security.platform_access import (
    PlatformAccessCondition,
    PlatformAccessPolicy,
)
from fred_pod.security.structure import (
    KeycloakUser,
    Principal,
)
from pydantic import ValidationError
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.security.models import Resource
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
)
from fred_core.security.platform_access.models import (
    PlatformAccessLinkJoinerRow,
    PlatformAccessLinkRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import (
    evaluate,
    extract_claims,
    normalize_attribute,
    path_key,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import OrganizationPermission, RebacReference
from fred_core.sql.accent_folding import (
    FOLDED_LETTERS,
    fold_accents,
    fold_text,
    search_spellings,
)
from fred_core.teams.metadata_store import TEAM_DESCRIPTION_PLACEHOLDER
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow


def policy() -> PlatformAccessPolicy:
    return PlatformAccessPolicy(
        conditions=[
            PlatformAccessCondition(
                claim=["profile", "unit"],
                operator="regex",
                value="accepted",
                case_sensitive=True,
            )
        ]
    )


def person(attribute=None, *, uid=None, issued=None, expires=None) -> KeycloakUser:
    return KeycloakUser(
        uid=uid or str(uuid4()),
        username="test-user",
        roles=[],
        admission_claims=extract_claims({"profile": {"unit": attribute}})[0],
        admission_issued_at=issued or time.time() - 10,
        admission_expires_at=expires or time.time() + 300,
    )


class MembershipEngine(NoopRebacEngine):
    def __init__(self):
        super().__init__()
        self.members: dict[str, set[str]] = {}
        self.admins: set[str] = set()
        self.unavailable = False

    async def _has_permission_raw(self, subject, permission, resource, **kwargs):
        if self.unavailable:
            raise RuntimeError("unavailable")
        if permission == OrganizationPermission.CAN_MANAGE_PLATFORM_ACCESS:
            return subject.id in self.admins
        return resource.id in self.members.get(subject.id, set())

    async def _lookup_resources_raw(self, subject, permission, resource_type, **kwargs):
        if self.unavailable:
            raise RuntimeError("unavailable")
        return [
            RebacReference(Resource.TEAM, team)
            for team in self.members.get(subject.id, set())
        ]


@pytest_asyncio.fixture
async def access(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'access.db'}")
    async with engine.begin() as connection:
        for model in (
            UserRow,
            TeamMetadataRow,
            PlatformAccessSettingsRow,
            PlatformAccessUserRow,
            PlatformAccessLinkRow,
            PlatformAccessLinkJoinerRow,
        ):
            await connection.run_sync(cast(Table, model.__table__).create)
    value = PlatformAccess(PlatformAccessStore(engine), MembershipEngine())
    initial = policy()
    assert initial is not None
    async with value.store.mutation() as session:
        session.add(
            PlatformAccessSettingsRow(
                id=1,
                policy=initial.model_dump(),
                revision=1,
                filtering_enabled=True,
            )
        )
    yield value
    await engine.dispose()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("accepted", True),
        (["other", "accepted"], True),
        ("notaccepted", False),
        ("", False),
        (None, False),
        (32, False),
        (["accepted", 32], False),
        ({"unit": "accepted"}, False),
    ],
)
def test_whole_bounded_matching(value, expected):
    assert (
        evaluate(policy(), extract_claims({"profile": {"unit": value}})[0]).matched
        is expected
    )
    assert normalize_attribute("a" * 1025) is None
    assert normalize_attribute(["accepted"] * 33) is None


def test_path_and_regex_policy_validation():
    for values in (
        {"claim": []},
        {"value": "["},
        {"claim": [""]},
        {"claim": ["a" * 257]},
    ):
        data = dict(claim=["unit"], operator="regex", value="accepted")
        data.update(values)
        with pytest.raises(ValidationError):
            PlatformAccessCondition.model_validate(data)
    user = person("accepted")
    assert "admission_claims" not in user.model_dump()
    assert "accepted" not in repr(user)


@pytest.mark.parametrize("directory", ["local", "keycloak"])
def test_administration_availability_and_bounded_authority(monkeypatch, directory):
    from fred_pod.security.structure import SecurityConfiguration

    from fred_core.security.platform_access import access_control

    security = SecurityConfiguration.model_validate(
        {
            "user": {
                "enabled": True,
                "realm_url": "https://idp.example.org",
                "client_id": "test",
            },
            "m2m": {
                "enabled": True,
                "realm_url": "https://idp.example.org",
                "client_id": "backend",
            },
            "rebac": {
                "type": "openfga",
                "enabled": True,
                "api_url": "https://fga.example.org",
                "timeout_millisec": 1000,
            },
            "user_directory": directory,
        }
    )
    monkeypatch.setattr(access_control, "_available", access_control._available)
    monkeypatch.setattr(access_control, "_installed", access_control._installed)
    access_control.configure_platform_access(security)
    security.m2m.enabled = False
    access_control.configure_platform_access(security)
    assert not access_control.platform_access_available()
    security.m2m.enabled = True
    assert security.rebac is not None
    security.rebac.timeout_millisec = None
    with pytest.raises(ValueError, match="timeout_millisec"):
        access_control.configure_platform_access(security)
    security.rebac.timeout_millisec = 1000
    access_control.configure_platform_access(security)
    assert access_control.platform_access_available()


def test_pathological_regex_is_bounded():
    config = policy()
    config.conditions[0].value = "(a+)+$"
    start = time.monotonic()
    assert not evaluate(
        config, {path_key(config.conditions[0].claim): "a" * 1023 + "!"}
    ).matched
    assert time.monotonic() - start < 0.5


@pytest.mark.asyncio
async def test_observation_is_monotonic_and_preserves_identity_cgu(access):
    user = person("accepted", issued=100, expires=time.time() + 300)
    await access.observe(user)
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(user.uid), session)
        row.gcuVersionAccepted = "2026-10"
        row.current_resources_storage_size = 42
    newer = user.model_copy(
        update={
            "admission_issued_at": 200,
            "admission_claims": {path_key(["profile", "unit"]): "other"},
        }
    )
    await access.observe(newer)
    row = await access.observe(user)
    assert row.admission_attribute == {path_key(["profile", "unit"]): "other"}
    assert row.gcuVersionAccepted == "2026-10"
    assert row.current_resources_storage_size == 42
    asserted = SimpleNamespace(uid=user.uid)
    assert not await access.eligible(asserted)
    contradiction = newer.model_copy(
        update={"admission_claims": {path_key(["profile", "unit"]): "accepted"}}
    )
    row = await access.observe(contradiction)
    assert row.admission_conflicted
    assert not await access.eligible(asserted)
    assert not await access.eligible(contradiction)


@pytest.mark.asyncio
async def test_delegated_evidence_requires_unexpired_compatible_path(access):
    user = person("accepted")
    assert await access.admitted(user)
    assert await access.admitted(SimpleNamespace(uid=user.uid))
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(user.uid), session)
        row.admission_expires_at = time.time() - 1
    assert not await access.admitted(SimpleNamespace(uid=user.uid))
    await access.observe(user.model_copy(update={"admission_issued_at": time.time()}))
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(user.uid), session)
        row.admission_attribute = {path_key(["obsolete"]): "accepted"}
    assert not await access.admitted(SimpleNamespace(uid=user.uid))


@pytest.mark.asyncio
async def test_live_independent_sources_and_revocation_across_instances(access):
    user = person("other")
    assert not await access.admitted(user)
    async with access.store.mutation() as session:
        await access.store.add_exception(UUID(user.uid), "admin", "manual", session)
        session.add(
            TeamMetadataRow(
                id="demo",
                name="Demo",
                description=TEAM_DESCRIPTION_PLACEHOLDER,
                platform_access_free=True,
            )
        )
    second = PlatformAccess(PlatformAccessStore(access.store.engine), access.rebac)
    assert await second.admitted(user)
    access.rebac.members[user.uid] = {"demo"}
    async with access.store.mutation() as session:
        await session.delete(await access.store.exception(UUID(user.uid), session))
    # Membership alone (added by hand or by a team link) is no Free source.
    assert not await second.admitted(user)
    link_id = uuid4()
    async with access.store.mutation() as session:
        session.add(
            PlatformAccessLinkRow(
                id=link_id,
                team_id="demo",
                token_hash="0" * 64,
                created_by="admin",
                created_at=datetime.now(timezone.utc),
                opening_count=0,
            )
        )
        await session.flush()
        session.add(
            PlatformAccessLinkJoinerRow(
                link_id=link_id,
                user_id=UUID(user.uid),
                joined_at=datetime.now(timezone.utc),
            )
        )
    assert await second.admitted(user)
    async with access.store.mutation() as session:
        (await session.get(PlatformAccessLinkRow, link_id)).kind = "team"
    assert not await second.admitted(user)
    async with access.store.mutation() as session:
        (await session.get(PlatformAccessLinkRow, link_id)).kind = "free"
    async with access.store.mutation() as session:
        team = await access.store.team("demo", session)
        team.platform_access_free = False
    assert not await second.admitted(user)
    async with access.store.mutation() as session:
        team = await access.store.team("demo", session)
        team.platform_access_free = True
    access.rebac.members[user.uid] = set()
    assert not await second.admitted(user)


@pytest.mark.asyncio
async def test_platform_admin_remains_admitted_until_live_role_removal(access):
    user = person("other")
    asserted = cast(Principal, SimpleNamespace(uid=user.uid))
    assert not await access.admitted(user)
    access.rebac.admins.add(user.uid)
    assert await access.admitted(user)
    assert await access.admitted(asserted)
    access.rebac.admins.remove(user.uid)
    assert not await access.admitted(user)
    assert not await access.admitted(asserted)


@pytest.mark.asyncio
async def test_authority_failure_is_unavailable_not_denial(access):
    user = person("other")
    async with access.store.mutation() as session:
        session.add(
            TeamMetadataRow(
                id="demo",
                name="Demo",
                description=TEAM_DESCRIPTION_PLACEHOLDER,
                platform_access_allowed=True,
            )
        )
    access.rebac.unavailable = True
    with pytest.raises(HTTPException) as error:
        await access.admitted(user)
    assert error.value.status_code == 503
    assert error.value.detail == "platform_access_unavailable"
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy = {"unexpected": "incompatible"}
    with pytest.raises(HTTPException) as error:
        await access.admitted(person("accepted"))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_normal_cached_and_query_only_principal_resolution_cannot_skip_gate(
    access, monkeypatch
):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from fred_core.security import oidc
    from fred_core.security.platform_access import access_control

    user = person("other")
    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", access)
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: user)
    active = AsyncMock()
    monkeypatch.setattr(oidc, "require_active_subject", active)
    resolve = AsyncMock(return_value=None)
    monkeypatch.setattr(oidc, "resolve_delegated_principal", resolve)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
    )
    for query_only in (False, True):
        with pytest.raises(HTTPException) as denial:
            await oidc.resolve_request_principal(request, user, query_only=query_only)
        assert denial.value.detail == "platform_access_denied"
    async with access.store.mutation() as session:
        await access.store.add_exception(UUID(user.uid), "admin", "manual", session)
    assert await oidc.get_current_user_without_gcu(request, "cached-token") is user
    async with access.store.mutation() as session:
        await session.delete(await access.store.exception(UUID(user.uid), session))
    with pytest.raises(HTTPException):
        await oidc.get_current_user_without_gcu(request, "cached-token")
    assert active.await_count == 4
    async with access.store.mutation() as session:
        (await access.store.settings(session)).filtering_enabled = False
    assert await oidc.resolve_request_principal(request, user) is user
    from fred_core.security.delegation import AssertedUser

    delegated = AssertedUser(
        uid=str(uuid4()), client_id="backend", run_id="run", agent_id="agent"
    )
    resolve.return_value = delegated
    assert await oidc.resolve_request_principal(request, user) is delegated


@pytest.mark.asyncio
async def test_own_denied_dependency_refuses_delegation_and_checks_suspension(
    access, monkeypatch
):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from fred_core.security import oidc

    user = person("other")
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: user)
    active = AsyncMock()
    monkeypatch.setattr(oidc, "require_active_subject", active)
    resolve = AsyncMock(return_value=None)
    monkeypatch.setattr(oidc, "resolve_delegated_principal", resolve)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
    )
    assert await oidc.get_own_user_for_platform_access(request, "bearer") is user
    active.assert_awaited_once_with(user)
    resolve.return_value = SimpleNamespace(uid=user.uid)
    with pytest.raises(HTTPException, match="requires_own_credential"):
        await oidc.get_own_user_for_platform_access(request, "workload")


@pytest.mark.asyncio
async def test_pure_service_skips_human_admission_but_asserted_person_does_not(
    access, monkeypatch
):
    from fred_core.security.platform_access import access_control

    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", access)
    service = person("other").model_copy(update={"service_account": True})
    await access_control.enforce_platform_access(service)
    with pytest.raises(HTTPException) as denied:
        await access_control.enforce_platform_access(
            cast(Principal, SimpleNamespace(uid=service.uid))
        )
    assert denied.value.detail == "platform_access_denied"


def rule(operator="contains", value="a.b", *, claim=None, sensitive=False):
    return PlatformAccessPolicy(
        conditions=[
            PlatformAccessCondition.model_validate(
                {
                    "claim": claim or ["profile", "unit"],
                    "operator": operator,
                    "value": value,
                    "case_sensitive": sensitive,
                }
            )
        ]
    )


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("contains", "aXb", False),
        ("contains", "A.B", True),
        ("equals", "a.b", True),
        ("equals", "prefix-a.b", False),
        ("not_contains", ["other", "A.B"], False),
        ("not_contains", ["other", "allowed"], True),
        ("not_equals", ["other", "A.B"], False),
        ("regex", "aXb", True),
    ],
)
def test_literal_array_and_regex_predicates(operator, value, expected):
    assert (
        evaluate(rule(operator), {path_key(["profile", "unit"]): value}).matched
        is expected
    )


@pytest.mark.parametrize(
    "operator", ["contains", "not_contains", "equals", "not_equals", "regex"]
)
@pytest.mark.parametrize("value", [None, "", [], [""], ["a.b", 1], 123, "x" * 1025])
def test_unavailable_values_never_match(operator, value):
    facts, invalid = extract_claims({"profile": {"unit": value}})
    result = evaluate(rule(operator), facts, invalid)
    assert not result.matched
    assert result.reasons == ["incompatible"]


def test_combinations_case_and_unambiguous_paths():
    first = PlatformAccessCondition(claim=["a.b"], operator="equals", value="Accepted")
    second = PlatformAccessCondition(
        claim=["a", "b"], operator="not_contains", value="blocked"
    )
    facts, invalid = extract_claims({"a.b": "accepted", "a": {"b": "blocked"}})
    assert not evaluate(
        PlatformAccessPolicy(conditions=[first, second]), facts, invalid
    ).matched
    assert evaluate(
        PlatformAccessPolicy(combination="any", conditions=[first, second]),
        facts,
        invalid,
    ).matched
    first.case_sensitive = True
    assert not evaluate(
        PlatformAccessPolicy(combination="any", conditions=[first, second]),
        facts,
        invalid,
    ).matched
    assert evaluate(rule("not_equals", claim=["absent"]), facts).reasons == ["missing"]


def test_policy_validation_and_claim_capture_bounds():
    for data in [
        {"conditions": []},
        {"conditions": [dict(claim=[" "], operator="equals", value="x")]},
        {"conditions": [dict(claim=["a"], operator="regex", value="[")]},
        {"conditions": [dict(claim=["a"], operator="equals", value="x" * 1025)]},
    ]:
        with pytest.raises(ValidationError):
            PlatformAccessPolicy.model_validate(data)
    facts, invalid = extract_claims({str(i): "value" for i in range(1000)})
    assert len(facts) + len(invalid - {path_key([])}) == 256
    assert path_key([]) in invalid


@pytest.mark.asyncio
async def test_live_policy_cached_facts_new_paths_and_delegation(access):
    human = person("accepted")
    human.admission_claims[path_key(["department"])] = "allowed"
    human.admission_claims[path_key(["unrelated"])] = "private"
    delegated = cast(Principal, SimpleNamespace(uid=human.uid))
    assert await access.admitted(human)
    observed = await access.store.user(UUID(human.uid))
    assert path_key(["unrelated"]) not in observed.admission_attribute
    second = PlatformAccess(PlatformAccessStore(access.store.engine), access.rebac)
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy = rule("equals", "allowed", claim=["department"]).model_dump()
        state.revision += 1
    assert not await second.admitted(delegated)
    assert await second.admitted(human)
    assert await access.admitted(delegated)
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy = rule("contains", "blocked", claim=["department"]).model_dump()
    assert not await second.admitted(human)
    assert not await access.admitted(delegated)


@pytest.mark.asyncio
async def test_older_evidence_cannot_overwrite_newer_on_path_change(access):
    old = person("accepted", issued=100)
    newer = old.model_copy(update={"admission_issued_at": 200})
    await access.admitted(newer)
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy = rule("equals", "accepted", claim=["new"]).model_dump()
    old.admission_claims[path_key(["new"])] = "accepted"
    await access.admitted(old)
    assert not await access.admitted(SimpleNamespace(uid=old.uid))
    assert (await access.store.user(UUID(old.uid))).admission_issued_at == 200


@pytest.mark.asyncio
async def test_delayed_observation_projects_current_policy_not_its_old_snapshot(access):
    human = person("accepted")
    human.admission_claims[path_key(["new"])] = "allowed"
    previous = access.policy(await access.state())
    await access.admitted(human)
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy = rule("equals", "allowed", claim=["new"]).model_dump()
    await access.admitted(human)
    row = await access.store.observe(human, previous)
    assert row.admission_attribute == {path_key(["new"]): "allowed"}
    assert await access.admitted(SimpleNamespace(uid=human.uid))


def test_object_claim_has_incompatible_explanation():
    facts, invalid = extract_claims({"profile": {"unit": "accepted"}})
    assert evaluate(rule(claim=["profile"]), facts, invalid).reasons == ["incompatible"]


@pytest.mark.asyncio
@pytest.mark.parametrize("service_account", [True, False])
async def test_pure_workload_mount_defers_account_status_but_tool_request_does_not(
    access, monkeypatch, service_account
):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from fred_core.security import oidc
    from fred_core.security.platform_access import access_control

    workload = person("other").model_copy(
        update={
            "service_account": service_account,
            "roles": [] if service_account else ["service_agent"],
        }
    )
    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", None)
    monkeypatch.setattr(
        oidc, "resolve_delegated_principal", AsyncMock(return_value=None)
    )
    active = AsyncMock(side_effect=HTTPException(503, "account_status_unavailable"))
    monkeypatch.setattr(oidc, "require_active_subject", active)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "query_string": b"",
            "headers": [],
        }
    )
    assert (
        await oidc.resolve_request_principal(request, workload, query_only=True)
        is workload
    )
    active.assert_not_awaited()
    with pytest.raises(HTTPException) as unavailable:
        await oidc.resolve_request_principal(request, workload)
    assert unavailable.value.detail == "account_status_unavailable"
    active.assert_awaited_once_with(workload)


@pytest.mark.asyncio
async def test_user_listing_filters_individual_exceptions_and_orders_each_mode(
    access,
):
    store = access.store
    # Ids run against the alphabet so id order and username order cannot coincide.
    names = ["zoe", "Bob", "alice", "bob", None, "Carol", None]
    ids = [UUID(int=100 - index) for index in range(len(names))]
    day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # zoe and Carol were granted together; the unnamed user last, Bob first.
    granted = {0: (2, "manual"), 1: (1, "t0"), 4: (3, "manual"), 5: (2, "manual")}
    async with store.mutation() as session:
        session.add_all(
            [
                UserRow(id=uid, username=name, email=f"{index}@example.org")
                for index, (uid, name) in enumerate(zip(ids, names))
            ]
        )
        await session.flush()
        session.add_all(
            [
                PlatformAccessUserRow(
                    user_id=ids[index],
                    source=source,
                    granted_by="actor",
                    granted_at=day + timedelta(days=offset),
                )
                for index, (offset, source) in granted.items()
            ]
        )

    def listed(rows):
        return [(row.username, row.id) for row in rows]

    # Without the filter: case-insensitive username, id as tiebreaker, no username last.
    everyone = [
        ("alice", ids[2]),
        ("bob", ids[3]),
        ("Bob", ids[1]),
        ("Carol", ids[5]),
        ("zoe", ids[0]),
        (None, ids[6]),
        (None, ids[4]),
    ]
    assert listed(await store.users(0, 25)) == everyone
    assert await store.user_count() == 7
    assert listed(await store.users(2, 3)) == everyone[2:5]

    # With the filter: newest grant first, a shared date falling back to the alphabet.
    exceptions = [(None, ids[4]), ("Carol", ids[5]), ("zoe", ids[0]), ("Bob", ids[1])]
    assert listed(await store.users(0, 25, exceptions_only=True)) == exceptions
    assert await store.user_count(exceptions_only=True) == 4
    pages = [
        listed(await store.users(offset, 3, exceptions_only=True))
        for offset in (0, 3, 6)
    ]
    assert pages == [exceptions[:3], exceptions[3:], []]
    one_by_one = [
        listed(await store.users(offset, 1, exceptions_only=True))[0]
        for offset in range(4)
    ]
    assert one_by_one == exceptions

    # The search narrows either set; the total follows the same set.
    assert listed(await store.users(0, 25, "BO")) == everyone[1:3]
    assert await store.user_count("BO") == 2
    assert listed(await store.users(0, 25, "BO", exceptions_only=True)) == [
        ("Bob", ids[1])
    ]
    assert await store.user_count("BO", exceptions_only=True) == 1
    assert (
        listed(await store.users(0, 25, "example", exceptions_only=True)) == exceptions
    )
    assert await store.users(0, 25, "alice", exceptions_only=True) == []
    assert await store.user_count("alice", exceptions_only=True) == 0

    # Each user comes with their own exception row, or none.
    paired = await store.users_with_exceptions(0, 25)
    assert [(user.id, row.source if row else None) for user, row in paired] == [
        (ids[2], None),
        (ids[3], None),
        (ids[1], "t0"),
        (ids[5], "manual"),
        (ids[0], "manual"),
        (ids[6], None),
        (ids[4], "manual"),
    ]
    filtered = await store.users_with_exceptions(0, 25, exceptions_only=True)
    assert all(row is not None and row.user_id == user.id for user, row in filtered)


@pytest.mark.asyncio
async def test_user_search_ignores_accents_and_case_on_both_sides(access):
    store = access.store
    people = [
        ("lea", "Léa", "Martin", "lea.martin@example.org"),
        ("ELODIE", "Élodie", "Petit", None),
        ("aicha", "Aïcha", "Moreau", None),
        ("helene", "Helene", "Dupont", None),
        ("francois", "François", "Nuñez", None),
        ("zoe", "ZOË", "ÅSTRÖM", None),
        ("olga", "ольга", "C++ & 50%", None),
        ("oeuvre", "œuvre", "straße", None),
    ]
    ids = [UUID(int=index + 1) for index in range(len(people))]
    async with store.mutation() as session:
        session.add_all(
            [
                UserRow(
                    id=uid,
                    username=username,
                    first_name=first,
                    last_name=last,
                    email=email,
                )
                for uid, (username, first, last, email) in zip(ids, people)
            ]
        )
        await session.flush()
        await store.add_exception(ids[1], "actor", "manual", session)
        await store.add_exception(ids[3], "actor", "manual", session)

    async def found(query: str, **options) -> set[str]:
        rows = await store.users(0, 25, query, **options)
        assert await store.user_count(query, **options) == len(rows)
        return {row.username for row in rows}

    # Accent on the stored side, on the query side, on both, and in either case.
    assert await found("lea") == {"lea"}
    assert await found("LÉA") == {"lea"}
    assert await found("hélène") == {"helene"}
    assert await found("HELENE") == {"helene"}
    assert await found("élodie") == {"ELODIE"}
    assert await found("elodie") == {"ELODIE"}
    assert await found("aicha") == await found("AÏCHA") == {"aicha"}
    assert await found("francois") == await found("nunez") == {"francois"}
    assert await found("astrom") == await found("zoe") == {"zoe"}
    # A letter typed as base + combining mark matches too.
    assert await found("e\u0301lodie") == {"ELODIE"}
    # Every column is still searched, and an unknown text still finds nothing.
    assert await found("EXAMPLE.org") == {"lea"}
    assert await found("zzz") == set()

    # Combined with the exception filter.
    assert await found("élo", exceptions_only=True) == {"ELODIE"}
    assert await found("hel", exceptions_only=True) == {"helene"}
    assert await found("lea", exceptions_only=True) == set()

    # Symbols, wildcards and other scripts behave as before; ligatures are not split.
    assert await found("c++ &") == {"olga"}
    assert await found("50%") == {"olga"}
    assert await found("Ольга") == await found("ольга") == {"olga"}
    assert await found("œuvre") == await found("straße") == {"oeuvre"}
    assert await found("oeuvre") == {"oeuvre"}  # the username, not the ligature
    assert await found("strasse") == set()


@pytest.mark.asyncio
async def test_user_search_finds_stored_capitals_outside_the_folding_table(access):
    from sqlalchemy import literal, select

    store = access.store
    people = [
        ("lukasz", "Łukasz"),
        ("soren", "SØREN"),
        ("zhanna", "Жанна"),
        ("omega", "Ωmega"),
    ]
    async with store.mutation() as session:
        session.add_all(
            [
                UserRow(id=UUID(int=index + 1), username=username, first_name=first)
                for index, (username, first) in enumerate(people)
            ]
        )
        # Whether this database lower() folds letters beyond ASCII (SQLite does not).
        unicode_lower = (
            await session.scalar(select(fold_accents(literal("ŁØЖΩ")))) == "łøжω"
        )

    async def found(query: str) -> set[str]:
        rows = await store.users(0, 25, query)
        assert await store.user_count(query) == len(rows)
        return {row.username for row in rows}

    # Typed as stored, a capital the table does not fold is always found.
    for username, first in people:
        assert await found(first) == {username}
        assert await found(first[:3]) == {username}
    # In the other case it is found wherever the database can fold it, on both sides alike.
    for username, first in people:
        assert await found(first.lower()) == ({username} if unicode_lower else set())
    # Stored in lower case, it is found in either case on every database.
    async with store.mutation() as session:
        session.add(UserRow(id=UUID(int=99), username="pawel", first_name="paweł"))
    assert (
        await found("PAWEŁ")
        == await found("Paweł")
        == await found("paweł")
        == {"pawel"}
    )


def test_search_spellings_leave_the_folding_to_the_database():
    # Only composed, never folded: the database applies one construct to both sides.
    assert search_spellings("Hélène") == ("Hélène",)
    assert search_spellings("ELODIE") == ("ELODIE",)
    assert search_spellings("E\u0301lodie") == ("Élodie",)
    # A capital an ASCII-only lower() would keep also goes in lower case.
    assert search_spellings("Łukasz") == ("Łukasz", "łukasz")
    assert search_spellings("Ольга") == ("Ольга", "ольга")
    assert search_spellings("łukasz ольга") == ("łukasz ольга",)


def test_accent_folding_table_and_postgresql_expression():
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    listed = "àâäáãåçéèêëíìîïñóòôöõúùûüýÿ"
    assert fold_text(listed) == "aaaaaaceeeeiiiinooooouuuuyy"
    assert fold_text(listed.upper()) == "aaaaaaceeeeiiiinooooouuuuyy"
    assert fold_text("Šárka Łukasz Þór æœßø") == "sarka łukasz þor æœßø"
    assert all(len(plain) == 1 and plain.isascii() for plain in FOLDED_LETTERS.values())
    # PostgreSQL folds in one pass, with the same letters as the Python side.
    statement = select(UserRow.id).where(PlatformAccessStore.user_search("Hé"))
    compiled = statement.compile(dialect=postgresql.dialect())
    assert str(compiled).count("translate(lower(users.") == 4
    assert "replace(" not in str(compiled)
    assert "".join(FOLDED_LETTERS) in compiled.params.values()
    # The typed text is a bind parameter folded by the same expression, never by Python.
    assert "Hé" in compiled.params.values()
    assert "Hé" not in str(compiled)
    assert "%he%" not in compiled.params.values()
    assert str(compiled).count("translate(lower(%(") == 4


@pytest.fixture
def fresh_warnings(monkeypatch):
    from fred_core.security.platform_access import store

    monkeypatch.setattr(store, "_last_warning", {})


@pytest.mark.asyncio
async def test_unreadable_joiner_table_fails_closed_and_logs_the_cause(
    access, caplog, fresh_warnings
):
    # A runtime role without SELECT on the joiner table broke the Free source
    # derivation in a live deployment; the cause must reach the logs.
    user = person("other")
    async with access.store.engine.begin() as connection:
        await connection.run_sync(
            cast(Table, PlatformAccessLinkJoinerRow.__table__).drop
        )
    logger = "fred_core.security.platform_access.store"
    with caplog.at_level("WARNING", logger=logger):
        for _ in range(3):
            with pytest.raises(HTTPException) as error:
                await access.admitted(user)
            assert (error.value.status_code, error.value.detail) == (
                503,
                "platform_access_unavailable",
            )
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    # One line per kind and minute, naming the error type, so an outage cannot flood.
    assert warnings == ["Platform access store unavailable: OperationalError"]


@pytest.mark.asyncio
async def test_unavailable_warning_never_logs_statement_parameters(
    access, caplog, fresh_warnings
):
    link_token = "plaintext-link-token-" + "x" * 22  # pragma: allowlist secret
    async with access.store.engine.begin() as connection:
        await connection.run_sync(cast(Table, PlatformAccessLinkRow.__table__).drop)
    with caplog.at_level("WARNING"):
        with pytest.raises(HTTPException):
            async with access.store.read() as session:
                await session.execute(
                    select(PlatformAccessLinkRow).where(
                        PlatformAccessLinkRow.token == link_token
                    )
                )
    assert caplog.records and link_token not in caplog.text
