# SPDX-License-Identifier: Apache-2.0
import time
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fred_pod.security.structure import (
    KeycloakUser,
    PlatformAccessConfiguration,
    Principal,
)
from pydantic import AnyHttpUrl, ValidationError
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.security.models import Resource
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    normalize_attribute,
)
from fred_core.security.platform_access.models import (
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import RebacEngine, RebacReference
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import GcuVersionsType, UserRow


def policy(**kwargs) -> PlatformAccessConfiguration:
    return PlatformAccessConfiguration(
        enabled=True,
        jwt_claim=["profile", "unit"],
        accepted_regex="accepted",
        supportLink=AnyHttpUrl("https://support.example.org"),
        **kwargs,
    )


def person(attribute=None, *, uid=None, issued=None, expires=None) -> KeycloakUser:
    return KeycloakUser(
        uid=uid or str(uuid4()),
        username="test-user",
        roles=[],
        admission_attribute=attribute,
        admission_issued_at=issued or time.time() - 10,
        admission_expires_at=expires or time.time() + 300,
    )


class MembershipEngine(NoopRebacEngine):
    def __init__(self):
        super().__init__()
        self.members: dict[str, set[str]] = {}
        self.unavailable = False

    async def _has_permission_raw(self, subject, permission, resource, **kwargs):
        if self.unavailable:
            raise RuntimeError("unavailable")
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
        ):
            await connection.run_sync(cast(Table, model.__table__).create)
    value = PlatformAccess(policy(), PlatformAccessStore(engine), MembershipEngine())
    async with value.store.mutation() as session:
        session.add(
            PlatformAccessSettingsRow(
                id=1, policy_fingerprint=value.fingerprint, filtering_enabled=True
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
    access = PlatformAccess(
        policy(), cast(PlatformAccessStore, None), cast(RebacEngine, None)
    )
    assert access.matches(value) is expected
    assert normalize_attribute("a" * 1025) is None
    assert normalize_attribute(["accepted"] * 33) is None


def test_path_and_regex_policy_validation():
    assert PlatformAccessConfiguration().enabled is False
    for values in (
        {"enabled": True},
        {"accepted_regex": "["},
        {"supportLink": "javascript:alert(1)"},
        {"supportLink": "http://support.example.org"},
        {
            "supportLink": "https://user:password@support.example.org"  # pragma: allowlist secret
        },
        {"jwt_claim": [""]},
        {"jwt_claim": ["a" * 257]},
    ):
        with pytest.raises(ValidationError):
            PlatformAccessConfiguration.model_validate(values)
    user = person("accepted")
    assert "admission_attribute" not in user.model_dump()
    assert "accepted" not in repr(user)


def test_enabled_configuration_refuses_unsafe_engines_and_legacy_gate(monkeypatch):
    from fred_pod.security.structure import SecurityConfiguration

    from fred_core.security.platform_access import access_control
    from fred_core.security.whitelist_access_control import access_control as legacy

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
            "user_directory": "local",
            "platform_access": policy(),
        }
    )
    monkeypatch.setattr(access_control, "_configured", access_control._configured)
    monkeypatch.setattr(access_control, "_installed", access_control._installed)
    monkeypatch.setattr(legacy, "is_whitelist_active", lambda: False)
    access_control.configure_platform_access(security)
    security.m2m.enabled = False
    with pytest.raises(ValueError, match="authentication"):
        access_control.configure_platform_access(security)
    security.m2m.enabled = True
    assert security.rebac is not None
    security.rebac.timeout_millisec = None
    with pytest.raises(ValueError, match="timeout_millisec"):
        access_control.configure_platform_access(security)
    security.rebac.timeout_millisec = 1000
    monkeypatch.setattr(legacy, "is_whitelist_active", lambda: True)
    with pytest.raises(ValueError, match="legacy"):
        access_control.configure_platform_access(security)


def test_pathological_regex_is_bounded():
    config = policy()
    config.accepted_regex = "(a+)+$"
    access = PlatformAccess(
        config, cast(PlatformAccessStore, None), cast(RebacEngine, None)
    )
    start = time.monotonic()
    assert not access.matches("a" * 1023 + "!")
    assert time.monotonic() - start < 0.5


@pytest.mark.asyncio
async def test_observation_is_monotonic_and_preserves_identity_cgu(access):
    user = person("accepted", issued=100, expires=time.time() + 300)
    await access.store.observe(user, access.path_fingerprint)
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(user.uid), session)
        row.gcuVersionAccepted = GcuVersionsType.V1
        row.current_resources_storage_size = 42
    newer = user.model_copy(
        update={"admission_issued_at": 200, "admission_attribute": "other"}
    )
    await access.store.observe(newer, access.path_fingerprint)
    row = await access.store.observe(user, access.path_fingerprint)
    assert row.admission_attribute == "other"
    assert row.gcuVersionAccepted == GcuVersionsType.V1
    assert row.current_resources_storage_size == 42
    asserted = SimpleNamespace(uid=user.uid)
    assert not await access.eligible(asserted)
    contradiction = newer.model_copy(update={"admission_attribute": "accepted"})
    row = await access.store.observe(contradiction, access.path_fingerprint)
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
    await access.store.observe(
        user.model_copy(update={"admission_issued_at": time.time()}),
        access.path_fingerprint,
    )
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(user.uid), session)
        row.admission_claim_path = "obsolete"
    assert not await access.admitted(SimpleNamespace(uid=user.uid))


@pytest.mark.asyncio
async def test_live_independent_sources_and_revocation_across_instances(access):
    user = person("other")
    assert not await access.admitted(user)
    async with access.store.mutation() as session:
        await access.store.add_exception(UUID(user.uid), "admin", "manual", session)
        session.add(TeamMetadataRow(id="demo", name="Demo", platform_access_free=True))
    second = PlatformAccess(
        access.config, PlatformAccessStore(access.store.engine), access.rebac
    )
    assert await second.admitted(user)
    access.rebac.members[user.uid] = {"demo"}
    async with access.store.mutation() as session:
        await session.delete(await access.store.exception(UUID(user.uid), session))
    assert await second.admitted(user)
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
async def test_authority_failure_is_unavailable_not_denial(access):
    user = person("other")
    async with access.store.mutation() as session:
        session.add(
            TeamMetadataRow(id="demo", name="Demo", platform_access_allowed=True)
        )
    access.rebac.unavailable = True
    with pytest.raises(HTTPException) as error:
        await access.admitted(user)
    assert error.value.status_code == 503
    assert error.value.detail == "platform_access_unavailable"
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy_fingerprint = "mismatch"
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
    monkeypatch.setattr(access_control, "_configured", access.config)
    monkeypatch.setattr(access_control, "_installed", access)
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: user)
    active = AsyncMock()
    monkeypatch.setattr(oidc, "require_active_subject", active)
    monkeypatch.setattr(
        oidc, "resolve_delegated_principal", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(oidc, "is_whitelist_active", lambda: False)
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

    monkeypatch.setattr(access_control, "_configured", access.config)
    monkeypatch.setattr(access_control, "_installed", access)
    service = person("other").model_copy(update={"service_account": True})
    await access_control.enforce_platform_access(service)
    with pytest.raises(HTTPException) as denied:
        await access_control.enforce_platform_access(
            cast(Principal, SimpleNamespace(uid=service.uid))
        )
    assert denied.value.detail == "platform_access_denied"
