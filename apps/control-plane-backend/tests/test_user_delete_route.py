"""`DELETE /users/{user_id}`: the only Fred operation that suspends a person's account.

Order: identity administration is resolved before anything changes; the ban is
written when account status is enforced; the identity-provider account is deleted last.
The person's other relations are kept.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from _account_status_test_doubles import AccountStatusRebacEngine, ban
from control_plane_backend.app.dependencies import attach_application_container
from control_plane_backend.users import api as users_api
from control_plane_backend.users.dependencies import get_user_service_dependencies
from fastapi import FastAPI
from fred_core import (
    AccountStatusError,
    DelegationConfig,
    KeycloackDisabled,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    enforce_account_status,
    get_current_user,
    initialize_delegation,
)
from fred_core.security.delegation import require_active_subject
from httpx import ASGITransport, AsyncClient
from keycloak.exceptions import KeycloakDeleteError

_PERSON = "synthetic-person"
_BYSTANDER = "synthetic-bystander"
_ROOT = "synthetic-root"
_TEAM = RebacReference(Resource.TEAM, "synthetic-team")
_MEMBERSHIP = Relation(
    subject=RebacReference(Resource.USER, _PERSON),
    relation=RelationType.TEAM_MEMBER,
    resource=_TEAM,
)
_DELETE = f"/users/{_PERSON}"


class _IdentityProvider:
    """`KeycloakAdmin.a_delete_user`: a 204 removes the account; any other status
    raises `KeycloakDeleteError` with that code (404 when the account is missing)."""

    def __init__(self, calls: list[str], accounts: set[str]) -> None:
        self.calls = calls
        self.accounts = accounts
        self.failure_code: int | None = None

    async def a_delete_user(self, user_id: str) -> dict:
        self.calls.append("delete_identity_account")
        if self.failure_code is not None:
            raise KeycloakDeleteError("synthetic failure", self.failure_code)
        if user_id not in self.accounts:
            raise KeycloakDeleteError("User not found", 404)
        self.accounts.discard(user_id)
        return {}


@dataclass
class _Deployment:
    client: AsyncClient
    rebac: AccountStatusRebacEngine
    identity: _IdentityProvider
    calls: list[str]


@asynccontextmanager
async def _deployment(
    *,
    rebac: AccountStatusRebacEngine | None = None,
    identity_administration: bool = True,
    user_directory: str = "keycloak",
) -> AsyncIterator[_Deployment]:
    calls: list[str] = []
    engine_under_test = rebac if rebac is not None else AccountStatusRebacEngine()
    engine_under_test.calls = calls
    # Stored state: one team membership and no suspension.
    engine_under_test.relations |= {_MEMBERSHIP}
    identity = _IdentityProvider(calls, {_PERSON, _BYSTANDER})

    async def root() -> str:
        return _ROOT

    async def no_favorites(user_id: str) -> None:
        calls.append("delete_favorites")

    container = SimpleNamespace(
        get_rebac_engine=lambda: engine_under_test,
        get_platform_bootstrap_store=lambda: SimpleNamespace(get_completed_by=root),
        get_prompt_store=lambda: SimpleNamespace(
            delete_favorites_for_user=no_favorites
        ),
    )
    app = FastAPI()
    app.include_router(users_api.router)
    users_api.register_exception_handlers(app)
    attach_application_container(app, container)  # type: ignore[arg-type]
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="synthetic-admin", username="synthetic-admin", roles=[]
    )
    app.dependency_overrides[get_user_service_dependencies] = lambda: SimpleNamespace(
        configuration=SimpleNamespace(
            security=SimpleNamespace(user_directory=user_directory)
        ),
        create_keycloak_admin_client=lambda: (
            identity if identity_administration else KeycloackDisabled()
        ),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield _Deployment(client, engine_under_test, identity, calls)


async def _assert_banned(rebac: AccountStatusRebacEngine) -> None:
    with pytest.raises(AccountStatusError):
        await rebac.require_active_account(_PERSON)
    await rebac.require_active_account(_BYSTANDER)


async def _can_read_team(rebac: AccountStatusRebacEngine, person_id: str) -> bool:
    return await rebac.has_permission(
        RebacReference(Resource.USER, person_id), TeamPermission.CAN_READ, _TEAM
    )


async def _assert_person_untouched(deployment: _Deployment) -> None:
    await deployment.rebac.require_active_account(_PERSON)
    assert _MEMBERSHIP in deployment.rebac.relations
    assert deployment.identity.accounts == {_PERSON, _BYSTANDER}


@pytest.mark.asyncio
async def test_delete_bans_before_identity_deletion() -> None:
    async with _deployment() as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert deployment.calls == [
            "suspend_account",
            "delete_favorites",
            "delete_identity_account",
        ]
        await _assert_banned(deployment.rebac)
        assert ban(_PERSON) in deployment.rebac.relations
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enforced", [True, False], ids=["delegation_on", "delegation_off"]
)
async def test_delete_keeps_the_persons_other_relations(enforced: bool) -> None:
    rebac = AccountStatusRebacEngine(requires_active_accounts=enforced)
    async with _deployment(rebac=rebac) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert "delete_all_relations_of_reference" not in deployment.calls
        kept = {_MEMBERSHIP}
        assert rebac.relations == (kept | {ban(_PERSON)} if enforced else kept)


@pytest.mark.asyncio
async def test_a_deleted_person_is_refused_at_their_next_request() -> None:
    person = KeycloakUser(uid=_PERSON, username="synthetic", roles=[])
    bystander = KeycloakUser(uid=_BYSTANDER, username="synthetic", roles=[])
    async with _deployment() as deployment:
        initialize_delegation(DelegationConfig(act_for_people=True))
        await enforce_account_status(deployment.rebac)
        await require_active_subject(person)

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        # The membership is still stored; the ban refuses the person anyway.
        assert _MEMBERSHIP in deployment.rebac.relations
        with pytest.raises(AccountStatusError):
            await require_active_subject(person)
        await require_active_subject(bystander)


@pytest.mark.asyncio
async def test_identity_failure_after_the_ban_leaves_the_person_banned() -> None:
    async with _deployment() as deployment:
        deployment.identity.failure_code = 500

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 500
        assert deployment.calls[-1] == "delete_identity_account"
        await _assert_banned(deployment.rebac)
        assert _PERSON in deployment.identity.accounts

        # A retry rewrites the same ban and removes the account.
        deployment.identity.failure_code = None
        deployment.calls.clear()
        retried = await deployment.client.delete(_DELETE)

        assert retried.status_code == 204
        assert deployment.calls == [
            "suspend_account",
            "delete_favorites",
            "delete_identity_account",
        ]
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
async def test_missing_identity_returns_not_found_after_the_ban() -> None:
    async with _deployment() as deployment:
        deployment.identity.accounts.discard(_PERSON)

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 404
        assert deployment.calls == [
            "suspend_account",
            "delete_favorites",
            "delete_identity_account",
        ]
        await _assert_banned(deployment.rebac)


@pytest.mark.asyncio
async def test_disabled_identity_administration_refuses_before_any_change() -> None:
    async with _deployment(identity_administration=False) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 503
        assert response.json() == {
            "detail": "Keycloak M2M is disabled; cannot perform user operations."
        }
        assert deployment.calls == []
        await deployment.rebac.require_active_account(_PERSON)
        assert _MEMBERSHIP in deployment.rebac.relations


@pytest.mark.asyncio
async def test_without_account_status_enforcement_delete_writes_no_ban() -> None:
    rebac = AccountStatusRebacEngine(requires_active_accounts=False)
    async with _deployment(rebac=rebac) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert deployment.calls == ["delete_favorites", "delete_identity_account"]
        assert ban(_PERSON) not in rebac.relations
        assert await _can_read_team(rebac, _PERSON)
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
@pytest.mark.parametrize("enforced", [True, False])
@pytest.mark.parametrize("path_id", ["%2A", "%23x", "team%23member"])
async def test_an_id_naming_no_person_is_refused_as_not_found_before_any_change(
    enforced: bool, path_id: str
) -> None:
    rebac = AccountStatusRebacEngine(requires_active_accounts=enforced)
    async with _deployment(rebac=rebac) as deployment:
        response = await deployment.client.delete(f"/users/{path_id}")

        assert response.status_code == 404
        assert deployment.calls == []
        assert deployment.rebac.relations == {_MEMBERSHIP}
        await _assert_person_untouched(deployment)


@pytest.mark.asyncio
async def test_deleting_the_bootstrap_root_is_refused_before_any_change() -> None:
    async with _deployment() as deployment:
        response = await deployment.client.delete(f"/users/{_ROOT}")

        assert response.status_code == 403
        assert deployment.calls == []
        assert ban(_ROOT) not in deployment.rebac.relations
        await _assert_person_untouched(deployment)


class _BanWriteFails(AccountStatusRebacEngine):
    async def suspend_account(self, user_id: str) -> str | None:
        self.calls.append("suspend_account")
        raise RuntimeError("synthetic store failure")


@pytest.mark.asyncio
async def test_a_failed_ban_write_keeps_the_identity_account() -> None:
    async with _deployment(rebac=_BanWriteFails()) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 500
        assert deployment.calls == ["suspend_account"]
        await _assert_person_untouched(deployment)


@pytest.mark.asyncio
async def test_local_delete_bans_person_without_calling_identity_provider() -> None:
    async with _deployment(user_directory="local") as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert deployment.calls == ["suspend_account"]
        assert deployment.identity.accounts == {_PERSON, _BYSTANDER}
        await _assert_banned(deployment.rebac)


@pytest.mark.asyncio
async def test_local_delete_still_protects_bootstrap_root() -> None:
    async with _deployment(user_directory="local") as deployment:
        response = await deployment.client.delete(f"/users/{_ROOT}")

        assert response.status_code == 403
        assert deployment.calls == []
