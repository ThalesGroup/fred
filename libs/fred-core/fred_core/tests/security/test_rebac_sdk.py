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

"""Tests for the named, fail-closed first-party ReBAC SDK."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Literal

import pytest
from pydantic import AnyHttpUrl, AnyUrl

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security import oidc
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac import rebac_sdk as rebac_sdk_module
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import (
    CapabilityPermission,
    RebacEngine,
    RebacReference,
    TeamPermission,
)
from fred_core.security.rebac.rebac_sdk import RebacSdk, rebac_sdk_factory
from fred_core.security.structure import (
    KeycloakUser,
    M2MSecurity,
    OpenFgaRebacConfig,
    SecurityConfiguration,
    UserSecurity,
)
from fred_core.tests.security.rebac_fakes import FakeRebacEngine

_USER = KeycloakUser(uid="alice", username="alice", roles=[])
_ENGINE_LOGGER = "fred_core.security.rebac.rebac_engine"
_REALM = AnyUrl("http://localhost:8080/realms/app")
_OPENFGA_ENV = "FIRST_PARTY_OPENFGA_TOKEN"


class _ClosingFakeRebacEngine(FakeRebacEngine):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0
        self.get_client_calls = 0

    async def get_client(self) -> object:
        self.get_client_calls += 1
        return object()

    async def close(self) -> None:
        self.close_calls += 1


class _FailingInitializationFakeRebacEngine(_ClosingFakeRebacEngine):
    async def get_client(self) -> object:
        self.get_client_calls += 1
        raise RuntimeError("OpenFGA unavailable")


@pytest.fixture(autouse=True)
def _restore_security_profile_globals() -> Iterator[None]:
    oidc_before = (
        oidc.STRICT_ISSUER,
        oidc.STRICT_AUDIENCE,
        oidc.KEYCLOAK_ENABLED,
        oidc.KEYCLOAK_URL,
        oidc.KEYCLOAK_JWKS_URL,
        oidc.KEYCLOAK_CLIENT_ID,
        oidc._JWKS_CLIENT,
    )
    yield
    (
        oidc.STRICT_ISSUER,
        oidc.STRICT_AUDIENCE,
        oidc.KEYCLOAK_ENABLED,
        oidc.KEYCLOAK_URL,
        oidc.KEYCLOAK_JWKS_URL,
        oidc.KEYCLOAK_CLIENT_ID,
        oidc._JWKS_CLIENT,
    ) = oidc_before


def _security(
    *,
    profile: Literal["c3"] | None = "c3",
    user_enabled: bool = True,
    user_client_id: str = "first-party-app",
    m2m_enabled: bool = True,
    rebac_enabled: bool = True,
    with_rebac: bool = True,
    create_store_if_needed: bool = False,
    sync_schema_on_init: bool = False,
    timeout_millisec: int | None = 5000,
) -> SecurityConfiguration:
    rebac = (
        OpenFgaRebacConfig(
            enabled=rebac_enabled,
            api_url=AnyHttpUrl("http://openfga:8080"),
            store_name="fred",
            create_store_if_needed=create_store_if_needed,
            sync_schema_on_init=sync_schema_on_init,
            token_env_var=_OPENFGA_ENV,
            timeout_millisec=timeout_millisec,
        )
        if with_rebac
        else None
    )
    return SecurityConfiguration(
        profile=profile,
        user=UserSecurity(
            enabled=user_enabled,
            realm_url=_REALM,
            client_id=user_client_id,
        ),
        m2m=M2MSecurity(
            enabled=m2m_enabled,
            realm_url=_REALM,
            client_id="first-party-app",
        ),
        rebac=rebac,
    )


def _sdk(engine: RebacEngine) -> RebacSdk:
    return rebac_sdk_module._RebacSdk(engine)


def _team_check(
    permission: TeamPermission, team_id: str
) -> tuple[RebacReference, TeamPermission, RebacReference]:
    return (
        RebacReference(type=Resource.USER, id=_USER.uid),
        permission,
        RebacReference(type=Resource.TEAM, id=team_id),
    )


def test_module_exports_only_the_named_sdk_surface_and_factory() -> None:
    assert rebac_sdk_module.__all__ == ["RebacSdk", "rebac_sdk_factory"]
    assert {name for name in vars(rebac_sdk_module) if not name.startswith("_")} == {
        "RebacSdk",
        "rebac_sdk_factory",
    }

    sdk = _sdk(FakeRebacEngine())
    assert {name for name in dir(sdk) if not name.startswith("_")} == {
        "check_application_access",
        "check_team_capability",
        "check_user_team_permission",
        "close",
    }
    assert not hasattr(sdk, "engine")
    assert not hasattr(sdk, "get_client")
    assert not hasattr(sdk, "rebac")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("security", "message"),
    [
        (_security(profile=None), "requires security.profile='c3'"),
        (_security(user_enabled=False), "security.user.enabled must be true"),
        (_security(m2m_enabled=False), "security.m2m.enabled must be true"),
        (_security(rebac_enabled=False), "security.rebac.enabled must be true"),
        (_security(with_rebac=False), "security.rebac.enabled must be true"),
    ],
)
async def test_factory_rejects_permissive_security_profiles(
    security: SecurityConfiguration, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await rebac_sdk_factory(security, kpi_writer=NoOpKPIWriter())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("security", "message"),
    [
        (
            _security(create_store_if_needed=True),
            "create_store_if_needed=false",
        ),
        (
            _security(sync_schema_on_init=True),
            "sync_schema_on_init=false",
        ),
    ],
)
async def test_factory_rejects_openfga_owner_configuration(
    security: SecurityConfiguration, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await rebac_sdk_factory(security, kpi_writer=NoOpKPIWriter())


@pytest.mark.asyncio
async def test_factory_rejects_unbounded_or_invalid_timeouts() -> None:
    for timeout in (None, -1, 0, 30_001):
        with pytest.raises(ValueError, match="timeout_millisec between 1 and 30000"):
            await rebac_sdk_factory(
                _security(timeout_millisec=timeout),
                kpi_writer=NoOpKPIWriter(),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("client_id", ["", "   "])
async def test_factory_rejects_empty_user_client_id_before_rebac_creation(
    monkeypatch: pytest.MonkeyPatch,
    client_id: str,
) -> None:
    factory_called = False

    def _factory(
        security: SecurityConfiguration,
        *,
        kpi_writer: BaseKPIWriter | None = None,
    ) -> RebacEngine:
        nonlocal factory_called
        factory_called = True
        return _ClosingFakeRebacEngine()

    monkeypatch.setattr(rebac_sdk_module, "_rebac_factory", _factory)

    with pytest.raises(
        ValueError,
        match=r"set security\.user\.client_id to the exact JWT audience",
    ):
        await rebac_sdk_factory(
            _security(user_client_id=client_id),
            kpi_writer=NoOpKPIWriter(),
        )

    assert factory_called is False


@pytest.mark.asyncio
async def test_factory_requires_a_process_kpi_writer() -> None:
    with pytest.raises(ValueError, match="requires a process KPI writer"):
        await rebac_sdk_factory(
            _security(),
            kpi_writer=None,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_factory_propagates_missing_openfga_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_OPENFGA_ENV, raising=False)

    with pytest.raises(ValueError, match=_OPENFGA_ENV):
        await rebac_sdk_factory(_security(), kpi_writer=NoOpKPIWriter())


@pytest.mark.asyncio
async def test_factory_passes_the_process_kpi_writer_to_rebac_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _ClosingFakeRebacEngine()
    writer = NoOpKPIWriter()
    received: list[tuple[SecurityConfiguration, BaseKPIWriter | None]] = []

    def _factory(
        security: SecurityConfiguration,
        *,
        kpi_writer: BaseKPIWriter | None = None,
    ) -> RebacEngine:
        received.append((security, kpi_writer))
        return engine

    monkeypatch.setattr(rebac_sdk_module, "_rebac_factory", _factory)
    security = _security()

    sdk = await rebac_sdk_factory(security, kpi_writer=writer)

    assert received == [(security, writer)]
    assert isinstance(sdk, rebac_sdk_module._RebacSdk)
    assert engine.get_client_calls == 1


@pytest.mark.asyncio
async def test_factory_propagates_openfga_initialization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _FailingInitializationFakeRebacEngine()

    def _factory(
        security: SecurityConfiguration,
        *,
        kpi_writer: BaseKPIWriter | None = None,
    ) -> RebacEngine:
        return engine

    monkeypatch.setattr(rebac_sdk_module, "_rebac_factory", _factory)

    with pytest.raises(RuntimeError, match="OpenFGA unavailable"):
        await rebac_sdk_factory(_security(), kpi_writer=NoOpKPIWriter())

    assert engine.get_client_calls == 1


@pytest.mark.asyncio
async def test_factory_initializes_the_process_jwt_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _factory(
        security: SecurityConfiguration,
        *,
        kpi_writer: BaseKPIWriter | None = None,
    ) -> RebacEngine:
        return _ClosingFakeRebacEngine()

    monkeypatch.setattr(rebac_sdk_module, "_rebac_factory", _factory)
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", "")
    monkeypatch.setattr(oidc, "KEYCLOAK_JWKS_URL", "")
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", "")
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", object())

    await rebac_sdk_factory(_security(), kpi_writer=NoOpKPIWriter())

    assert oidc.KEYCLOAK_ENABLED is True
    assert oidc.KEYCLOAK_URL == str(_REALM)
    assert oidc.KEYCLOAK_JWKS_URL == f"{_REALM}/protocol/openid-connect/certs"
    assert oidc.KEYCLOAK_CLIENT_ID == "first-party-app"
    assert oidc._JWKS_CLIENT is None
    assert oidc.STRICT_ISSUER is True
    assert oidc.STRICT_AUDIENCE is True
    assert bool(oidc.STRICT_AUDIENCE and oidc.KEYCLOAK_CLIENT_ID) is True


@pytest.mark.asyncio
async def test_factory_rejects_a_disabled_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _factory(
        security: SecurityConfiguration,
        *,
        kpi_writer: BaseKPIWriter | None = None,
    ) -> RebacEngine:
        return NoopRebacEngine()

    monkeypatch.setattr(rebac_sdk_module, "_rebac_factory", _factory)

    with pytest.raises(ValueError, match="requires an enabled OpenFGA engine"):
        await rebac_sdk_factory(_security(), kpi_writer=NoOpKPIWriter())


def test_private_implementation_rejects_noop_engine() -> None:
    with pytest.raises(ValueError, match="requires an enabled OpenFGA engine"):
        _sdk(NoopRebacEngine())


@pytest.mark.asyncio
async def test_check_user_team_permission_passes_through_to_the_engine() -> None:
    rebac = FakeRebacEngine(permitted=True)

    result = await _sdk(rebac).check_user_team_permission(
        _USER, TeamPermission.CAN_USE_TEAM_APPLICATIONS, "team-1"
    )

    assert result is None
    assert rebac.checked == [
        _team_check(TeamPermission.CAN_USE_TEAM_APPLICATIONS, "team-1")
    ]


@pytest.mark.asyncio
async def test_check_user_team_permission_raises_on_denial() -> None:
    rebac = FakeRebacEngine(permitted=False)

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_user_team_permission(
            _USER, TeamPermission.CAN_USE_TEAM_APPLICATIONS, "team-1"
        )

    assert denial.value.user_id == _USER.uid
    assert denial.value.actor_uid == _USER.uid
    assert denial.value.subject_type == Resource.USER
    assert denial.value.subject_id == _USER.uid


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", ["personal", "personal-alice"])
async def test_check_user_team_permission_refuses_personal_spaces(
    team_id: str,
) -> None:
    rebac = FakeRebacEngine(permitted=True)

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_user_team_permission(
            _USER, TeamPermission.CAN_USE_TEAM_APPLICATIONS, team_id
        )

    assert denial.value.user_id == _USER.uid
    assert denial.value.actor_uid == _USER.uid
    assert rebac.checked == []


@pytest.mark.asyncio
async def test_check_team_capability_is_one_check_on_the_capability() -> None:
    rebac = FakeRebacEngine(permitted=True)

    await _sdk(rebac).check_team_capability("team-1", "app__acme-forecast")

    assert rebac.checked == [
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            CapabilityPermission.CAN_USE,
            RebacReference(type=Resource.CAPABILITY, id="app__acme-forecast"),
        )
    ]


@pytest.mark.asyncio
async def test_check_team_capability_raises_a_permission_error_on_denial() -> None:
    rebac = FakeRebacEngine(permitted=False)

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_team_capability("team-1", "app__acme-forecast")

    assert isinstance(denial.value, PermissionError)
    assert denial.value.user_id == "team-1"
    assert denial.value.actor_uid is None
    assert denial.value.subject_type == Resource.TEAM
    assert denial.value.subject_id == "team-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", ["personal", "personal-alice"])
async def test_check_team_capability_refuses_personal_spaces(team_id: str) -> None:
    rebac = FakeRebacEngine(permitted=True)

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_team_capability(team_id, "app__acme-forecast")

    assert denial.value.user_id == team_id
    assert denial.value.actor_uid is None
    assert denial.value.subject_type == Resource.TEAM
    assert denial.value.subject_id == team_id
    assert rebac.checked == []


@pytest.mark.asyncio
async def test_check_team_capability_denial_reaches_the_rebac_denial_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rebac = FakeRebacEngine(permitted=False)

    with caplog.at_level(logging.WARNING, logger=_ENGINE_LOGGER):
        caplog.clear()
        with pytest.raises(AuthorizationError):
            await _sdk(rebac).check_team_capability("team-1", "app__acme-forecast")

    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == _ENGINE_LOGGER
    ] == [
        "ReBAC authorization denied: subject=team:team-1 permission=can_use "
        "resource=capability:app__acme-forecast"
    ]


@pytest.mark.asyncio
async def test_check_application_access_asks_membership_then_the_app_grant() -> None:
    rebac = FakeRebacEngine(permitted=True)

    await _sdk(rebac).check_application_access(
        _USER, team_id="team-1", app_id="acme-forecast"
    )

    assert rebac.checked == [
        _team_check(TeamPermission.CAN_USE_TEAM_APPLICATIONS, "team-1"),
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            CapabilityPermission.CAN_USE,
            RebacReference(type=Resource.CAPABILITY, id="app__acme-forecast"),
        ),
    ]


@pytest.mark.asyncio
async def test_check_application_access_sends_the_team_edge_with_the_grant_check() -> (
    None
):
    rebac = FakeRebacEngine(permitted=True)

    await _sdk(rebac).check_application_access(
        _USER, team_id="team-1", app_id="acme-forecast"
    )

    membership_context, grant_context = rebac.checked_contextual_relations
    assert membership_context == []
    assert [relation.relation.value for relation in grant_context] == ["team"]


@pytest.mark.asyncio
async def test_check_application_access_stops_at_membership_for_a_non_member() -> None:
    rebac = FakeRebacEngine(permitted=False)

    with pytest.raises(AuthorizationError):
        await _sdk(rebac).check_application_access(
            _USER, team_id="team-1", app_id="acme-forecast"
        )

    assert len(rebac.checked) == 1


@pytest.mark.parametrize("team_id", ["personal-alice", "personal"])
@pytest.mark.asyncio
async def test_check_application_access_refuses_personal_spaces(team_id: str) -> None:
    rebac = FakeRebacEngine(permitted=True)

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_application_access(
            _USER, team_id=team_id, app_id="acme-forecast"
        )

    assert rebac.checked == []
    assert denial.value.user_id == _USER.uid
    assert denial.value.actor_uid == _USER.uid


@pytest.mark.asyncio
async def test_check_application_access_denies_a_member_whose_team_lacks_the_grant() -> (
    None
):
    rebac = FakeRebacEngine(
        permitted=True, denied_permissions={CapabilityPermission.CAN_USE}
    )

    with pytest.raises(AuthorizationError) as denial:
        await _sdk(rebac).check_application_access(
            _USER, team_id="team-1", app_id="acme-forecast"
        )

    assert [permission for _subject, permission, _resource in rebac.checked] == [
        TeamPermission.CAN_USE_TEAM_APPLICATIONS,
        CapabilityPermission.CAN_USE,
    ]
    assert denial.value.user_id == _USER.uid
    assert denial.value.actor_uid == _USER.uid
    assert denial.value.subject_type == Resource.TEAM
    assert denial.value.subject_id == "team-1"


@pytest.mark.asyncio
async def test_close_delegates_to_the_owned_engine() -> None:
    engine = _ClosingFakeRebacEngine()
    sdk = _sdk(engine)

    await sdk.close()

    assert engine.close_calls == 1


@pytest.mark.asyncio
async def test_async_context_manager_reuses_and_closes_the_sdk() -> None:
    engine = _ClosingFakeRebacEngine()
    sdk = _sdk(engine)

    async with sdk as entered:
        assert entered is sdk
        await entered.check_team_capability("team-1", "app__acme-forecast")

    assert engine.close_calls == 1
    assert len(engine.checked) == 1
