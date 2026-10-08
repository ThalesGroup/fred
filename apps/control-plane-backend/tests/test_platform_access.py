# SPDX-License-Identifier: Apache-2.0
import time
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.platform_access import api, service
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import UserTeamRelation
from fastapi import FastAPI, HTTPException
from fred_core.common import TeamId
from fred_core.security.models import Resource
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.platform_access.models import (
    PlatformAccessLinkRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import (
    extract_claims,
    path_key,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import RebacReference, RelationType
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from fred_pod.security.platform_access import (
    PlatformAccessCondition,
    PlatformAccessPolicy,
)
from fred_pod.security.structure import (
    KeycloakUser,
    Principal,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine


class MembershipEngine(NoopRebacEngine):
    def __init__(self):
        super().__init__()
        self.members: dict[str, set[str]] = {}
        self.admin = True
        self.writes = []
        self.write_failure = False

    async def _lookup_resources_raw(self, subject, permission, resource_type, **kwargs):
        return [
            RebacReference(Resource.TEAM, team)
            for team in self.members.get(subject.id, set())
        ]

    async def _has_permission_raw(self, subject, permission, resource, **kwargs):
        return resource.id in self.members.get(subject.id, set())

    async def check_user_permission_or_raise(self, *args, **kwargs):
        if not self.admin:
            raise HTTPException(403, "forbidden")

    async def add_relation(self, relation, *, actor_uid=None):
        if self.write_failure:
            raise RuntimeError("write failed")
        self.writes.append(relation)
        self.members.setdefault(relation.subject.id, set()).add(relation.resource.id)
        return None


@pytest_asyncio.fixture
async def access(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admission.sqlite'}")
    async with engine.begin() as connection:
        for model in (
            UserRow,
            TeamMetadataRow,
            PlatformAccessLinkRow,
            PlatformAccessSettingsRow,
            PlatformAccessUserRow,
        ):
            await connection.run_sync(cast(Table, model.__table__).create)
    value = PlatformAccess(PlatformAccessStore(engine), MembershipEngine())
    initial = draft()
    async with value.store.mutation() as session:
        session.add(
            PlatformAccessSettingsRow(
                id=1,
                policy=initial.model_dump(),
                revision=1,
                filtering_enabled=False,
            )
        )
        session.add(
            TeamMetadataRow(
                id="demo",
                name="Demonstration",
                joining_mode="invite_only",
                visibility="private",
            )
        )
    yield value
    await engine.dispose()


def user(attribute="other"):
    return KeycloakUser(
        uid=str(uuid4()),
        username="Person",
        roles=[],
        admission_claims=extract_claims(
            {"profile": {"attribute": attribute}, "attribute": attribute}
        )[0],
        admission_issued_at=time.time() - 1,
        admission_expires_at=time.time() + 300,
    )


@pytest.mark.asyncio
async def test_t0_once_and_deleted_entries_never_return(access):
    actor, existing, matching = user(), user(), user("accepted")
    for person in (actor, existing, matching):
        await access.observe(person)
    preview = await service.t0(access)
    assert (preview.candidates, preview.matching, preview.completed_at) == (2, 1, None)
    result = await service.t0(access, actor)
    assert result.completed_at
    assert (await access.store.exception(UUID(existing.uid))).source == "t0"
    assert await access.store.exception(UUID(matching.uid)) is None
    await service.set_user(access, actor, UUID(existing.uid), False)
    later = user()
    await access.observe(later)
    again = await service.t0(access, actor)
    assert again.completed_at == result.completed_at.replace(tzinfo=None)
    assert await access.store.exception(UUID(existing.uid)) is None
    assert await access.store.exception(UUID(later.uid)) is None


@pytest.mark.asyncio
async def test_filter_and_exception_mutations_preserve_acting_admin(access):
    actor = user()
    await access.observe(actor)
    with pytest.raises(HTTPException, match="platform_access_actor_lockout"):
        await service.set_filtering(access, actor, True)
    assert not (await access.state()).filtering_enabled
    await service.set_user(access, actor, UUID(actor.uid), True)
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException):
        await service.set_user(access, actor, UUID(actor.uid), False)
    assert await access.admitted(actor)
    await service.set_filtering(access, actor, False)
    await service.set_user(access, actor, UUID(actor.uid), False)


@pytest.mark.asyncio
async def test_own_eligible_team_cannot_be_revoked_by_access_policy_actor(access):
    actor = user()
    await access.observe(actor)
    await service.set_team(access, actor, "demo", True, False)
    access.rebac.members[actor.uid] = {"demo"}
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException):
        await service.set_team(access, actor, "demo", False, False)
    assert await access.admitted(actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["v1", "2026-10"])
async def test_independent_free_links_suspension_revocation_and_private_enrollment(
    access, version
):
    actor, newcomer = user("accepted"), user()
    await access.observe(actor)
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo", user("accepted"))
    assert len(token) == 43
    links = await service.list_links(access, "demo", 0, 25)
    assert token not in links.model_dump_json()
    assert await service.reveal_link(access, "demo", links.items[0].id) == token
    assert (await service.preview_link(access, newcomer, token, version)).cgu_required
    with pytest.raises(HTTPException, match="user_not_accept_gcu"):
        await service.enroll(access, newcomer, token, version)
    assert access.rebac.writes == []
    with pytest.raises(HTTPException, match="gcu_version_changed"):
        await service.accept_cgu(access, newcomer, token, "outdated", version)
    await service.accept_cgu(access, newcomer, token, version, version)
    assert not (
        await service.preview_link(access, newcomer, token, version)
    ).cgu_required
    assert (await service.preview_link(access, newcomer, token, "next")).cgu_required
    await service.set_filtering(access, actor, True)
    enrolled = await service.enroll(access, newcomer, token, version)
    assert enrolled.admitted
    assert access.rebac.writes[0].relation == RelationType.TEAM_MEMBER
    await service.enroll(access, newcomer, token, version)
    assert len(access.rebac.writes) == 1
    sources = (await service.users_page(access, 0, 25, "")).items
    assert any(
        source.kind == "free" and source.team_id == "demo"
        for row in sources
        if row.user_id == newcomer.uid
        for source in row.sources
    )
    team = (await access.store.teams())[0]
    assert (team.visibility, team.joining_mode) == ("private", "invite_only")
    replacement = await service.generate_link(access, "demo", user("accepted"))
    await service.enroll(access, user(), token, None)
    await service.revoke_link(access, "demo", links.items[0].id)
    with pytest.raises(HTTPException):
        await service.enroll(access, user(), token, None)
    assert await access.admitted(newcomer)
    await service.set_team(access, actor, "demo", False, False)
    assert not await access.admitted(newcomer)
    await service.set_team(access, actor, "demo", False, True)
    await service.enroll(access, user(), replacement, None)


@pytest.mark.asyncio
async def test_failed_membership_write_can_retry_without_granting_admin(access):
    actor, newcomer = user(), user()
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo", user("accepted"))
    access.rebac.write_failure = True
    with pytest.raises(HTTPException) as unavailable:
        await service.enroll(access, newcomer, token, None)
    assert unavailable.value.status_code == 503
    access.rebac.write_failure = False
    await service.enroll(access, newcomer, token, None)
    assert len(access.rebac.writes) == 1
    assert access.rebac.writes[0].subject.id == newcomer.uid


@pytest.mark.asyncio
async def test_personal_team_and_nonfree_link_are_refused(access):
    with pytest.raises(HTTPException):
        await service.set_team(access, user(), "personal-user", True, True)
    with pytest.raises(HTTPException):
        await service.generate_link(access, "demo", user("accepted"))


def test_ordinary_team_update_cannot_set_admission_state():
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    body = UpdateTeamRequest.model_validate(
        {
            "name": "Demo",
            "platform_access_allowed": True,
            "platform_access_free": True,
            "enrollment_token_hash": "caller-supplied",
        }
    )
    assert body.model_dump(exclude_unset=True) == {"name": "Demo"}


@pytest.mark.asyncio
async def test_admin_endpoints_reject_nonplatform_admins(access):
    access.rebac.admin = False
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/admin/platform/access",
            "/admin/platform/access/users",
            "/admin/platform/access/teams",
            "/admin/platform/access/t0-preview",
        ):
            response = await client.get(path)
            assert response.status_code == 403
        response = await client.post("/admin/platform/access/t0-import")
        assert response.status_code == 403
        response = await client.patch(
            "/admin/platform/access", json={"filtering_enabled": True}
        )
        assert response.status_code == 403
        target = str(uuid4())
        response = await client.post(
            "/admin/platform/access/users", json={"user_ids": [target]}
        )
        assert response.status_code == 403
        response = await client.put(f"/admin/platform/access/users/{target}")
        assert response.status_code == 403
        response = await client.delete(f"/admin/platform/access/users/{target}")
        assert response.status_code == 403
        response = await client.patch(
            "/admin/platform/access/teams/demo",
            json={"allowed": True, "free": True},
        )
        assert response.status_code == 403
        response = await client.post(
            "/admin/platform/access/teams/demo/enrollment-link"
        )
        assert response.status_code == 403
    assert not (await access.state()).filtering_enabled


@pytest.mark.asyncio
async def test_denied_self_status_does_not_provision_team_or_directory(access):
    person = user()
    actor = user("accepted")
    await service.set_filtering(access, actor, True)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_own_user_for_platform_access] = lambda: person
    app.dependency_overrides[get_application_configuration] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version="v1")
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/platform-access/status")
    assert response.json() == {"admitted": False, "cgu_required": True}
    assert await access.store.user(UUID(person.uid)) is not None
    assert len(await access.store.teams()) == 1


@pytest_asyncio.fixture
async def pg_access(monkeypatch):
    import os

    import sqlalchemy as sa

    url = os.environ.get("FRED_PLATFORM_ACCESS_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set FRED_PLATFORM_ACCESS_TEST_DATABASE_URL to an isolated PostgreSQL fixture"
        )
    admin_engine = create_async_engine(url)
    schema = f"access_test_{uuid4().hex}"
    async with admin_engine.begin() as connection:
        await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as connection:
            for model in (
                UserRow,
                TeamMetadataRow,
                PlatformAccessLinkRow,
                PlatformAccessSettingsRow,
                PlatformAccessUserRow,
            ):
                await connection.run_sync(cast(Table, model.__table__).create)
        value = PlatformAccess(PlatformAccessStore(engine), MembershipEngine())
        initial = draft(claim=["attribute"])
        async with value.store.mutation() as session:
            session.add(
                PlatformAccessSettingsRow(
                    id=1,
                    policy=initial.model_dump(),
                    revision=1,
                    filtering_enabled=False,
                )
            )
            session.add(
                TeamMetadataRow(id="demo", name="Demo", platform_access_free=True)
            )
        yield value
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_pg_t0_and_fixed_population(pg_access):
    import asyncio

    actor, existing = user("accepted"), user()
    await pg_access.observe(existing)
    results = await asyncio.gather(
        service.t0(pg_access, actor), service.t0(pg_access, actor)
    )
    assert results[0].completed_at == results[1].completed_at
    await service.set_user(pg_access, actor, UUID(existing.uid), False)
    later = user()
    await pg_access.observe(later)
    await service.t0(pg_access, actor)
    assert await pg_access.store.exception(UUID(existing.uid)) is None
    assert await pg_access.store.exception(UUID(later.uid)) is None


@pytest.mark.asyncio
async def test_pg_enrollment_serializes_free_revocation(pg_access, monkeypatch):
    import asyncio

    actor, newcomer = user("accepted"), user()
    token = await service.generate_link(pg_access, "demo", user("accepted"))
    await service.set_filtering(pg_access, actor, True)
    started, release = asyncio.Event(), asyncio.Event()
    original = pg_access.rebac.add_relation

    async def blocked_write(relation):
        started.set()
        await release.wait()
        return await original(relation)

    monkeypatch.setattr(pg_access.rebac, "add_relation", blocked_write)
    enrollment = asyncio.create_task(service.enroll(pg_access, newcomer, token, None))
    await asyncio.wait_for(started.wait(), timeout=5)
    revocation = asyncio.create_task(
        service.set_team(pg_access, actor, "demo", False, False)
    )
    await asyncio.sleep(0.05)
    assert not revocation.done()
    release.set()
    await asyncio.gather(enrollment, revocation)
    second = PlatformAccess(
        PlatformAccessStore(pg_access.store.engine), pg_access.rebac
    )
    assert not await second.admitted(newcomer)
    with pytest.raises(HTTPException):
        await service.enroll(second, user(), token, None)


@pytest.mark.asyncio
async def test_pg_link_disabled_before_locked_enrollment_refuses(pg_access):
    import asyncio

    token = await service.generate_link(pg_access, "demo", user("accepted"))
    newcomer = user()
    await pg_access.observe(newcomer)
    async with pg_access.store.mutation() as session:
        team = await pg_access.store.team("demo", session)
        team.platform_access_free = False
        await session.flush()
        enrolling = asyncio.create_task(
            service.enroll(pg_access, newcomer, token, None)
        )
        await asyncio.sleep(0.05)
        assert not enrolling.done()
    with pytest.raises(HTTPException):
        await asyncio.wait_for(enrolling, timeout=10)
    assert pg_access.rebac.writes == []


@pytest.mark.asyncio
async def test_pg_startup_empty_authority_saved_policy_and_missing_schema(
    pg_access, monkeypatch
):
    import sqlalchemy as sa
    from fred_core.security.platform_access import access_control
    from fred_pod.security.structure import SecurityConfiguration

    class EnforcedEngine(MembershipEngine):
        @property
        def enabled(self):
            return True

        @property
        def requires_active_accounts(self):
            return True

    monkeypatch.setattr(access_control, "_installed", None)
    security = SecurityConfiguration.model_validate(
        {
            "user": {
                "enabled": True,
                "realm_url": "https://idp.example.org",
                "client_id": "ui",
            },
            "m2m": {
                "enabled": True,
                "realm_url": "https://idp.example.org",
                "client_id": "api",
            },
            "rebac": {
                "type": "openfga",
                "enabled": True,
                "api_url": "https://fga.example.org",
            },
        }
    )
    engine, rebac = pg_access.store.engine, EnforcedEngine()
    async with engine.begin() as connection:
        await connection.execute(sa.delete(PlatformAccessSettingsRow))
    with pytest.raises(HTTPException, match="platform_access_unavailable"):
        await access_control.initialize_platform_access(security, engine, rebac)
    assert await pg_access.store.settings() is None
    await access_control.initialize_platform_access(
        security, engine, rebac, authority=True
    )
    assert not (await pg_access.state()).filtering_enabled
    state = await pg_access.state()
    assert state.policy is None and state.revision == 0
    actor = user("accepted")
    await service.save_policy(pg_access, actor, draft(), 0)
    await service.set_filtering(pg_access, actor, True)
    await access_control.initialize_platform_access(security, engine, rebac)
    await access_control.initialize_platform_access(
        security, engine, rebac, authority=True
    )
    state = await pg_access.state()
    assert state.policy == draft().model_dump()
    assert state.revision == 1 and state.filtering_enabled
    async with engine.begin() as connection:
        await connection.execute(sa.text("DROP TABLE platform_access_links"))
    await access_control.initialize_platform_access(security, engine, rebac)
    with pytest.raises(RuntimeError, match="platform_access_links"):
        await access_control.initialize_platform_access(
            security, engine, rebac, authority=True
        )
    async with engine.begin() as connection:
        await connection.execute(sa.text("DROP TABLE platform_access_users"))
    with pytest.raises(RuntimeError, match="platform_access_users"):
        await access_control.initialize_platform_access(
            security, engine, rebac, authority=True
        )


def draft(value="accepted", claim=None):
    return PlatformAccessPolicy(
        conditions=[
            PlatformAccessCondition(
                claim=claim or ["profile", "attribute"], operator="equals", value=value
            )
        ]
    )


@pytest.mark.asyncio
async def test_policy_preview_is_side_effect_free_and_uses_enabled_filter_semantics(
    access,
):
    actor = user("accepted")
    actor.admission_claims[path_key(["new"])] = "secret"
    await access.observe(actor)
    before = (await access.store.user(UUID(actor.uid))).admission_attribute
    result = await service.preview_policy(access, actor, draft("secret", ["new"]))
    assert result.matched and result.admitted
    denied = await service.preview_policy(access, actor, draft("absent"))
    assert not denied.matched and not denied.admitted
    assert (await access.store.user(UUID(actor.uid))).admission_attribute == before
    assert (await access.state()).revision == 1
    await service.set_user(access, actor, UUID(actor.uid), True)
    assert (await service.preview_policy(access, actor, draft("absent"))).admitted


@pytest.mark.asyncio
async def test_policy_save_revision_and_atomic_self_lockout(access):
    actor = user("accepted")
    await access.observe(actor)
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException, match="platform_access_actor_lockout"):
        await service.save_policy(access, actor, draft("denied"), 1)
    assert (await access.state()).revision == 1
    result = await service.save_policy(access, actor, draft("ACCEPTED"), 1)
    assert result.revision == 2
    with pytest.raises(HTTPException, match="platform_access_policy_conflict"):
        await service.save_policy(access, actor, draft("different"), 1)
    assert (await access.state()).policy == draft("ACCEPTED").model_dump()


@pytest.mark.asyncio
async def test_unseeded_policy_requires_explicit_rule_before_activation(access):
    actor = user()
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy, state.revision = None, 0
    await access.observe(actor)
    await service.set_user(access, actor, UUID(actor.uid), True)
    with pytest.raises(HTTPException, match="platform_access_policy_required"):
        await service.set_filtering(access, actor, True)
    await service.save_policy(access, actor, draft(), 0)
    await service.set_filtering(access, actor, True)
    assert await access.admitted(actor)


@pytest.mark.asyncio
async def test_rule_endpoints_permissions_validation_and_retired_catalog(access):
    actor = user("accepted")
    await access.observe(actor)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/admin/platform/access/claims")).status_code == 404
        response = await client.post(
            "/admin/platform/access/policy-preview", json=draft().model_dump()
        )
        assert response.json()["matched"]
        saved = await client.put(
            "/admin/platform/access/policy",
            json={"expected_revision": 1, "policy": draft().model_dump()},
        )
        assert saved.json()["revision"] == 2
        response = await client.put(
            "/admin/platform/access/policy",
            json={"expected_revision": 1, "policy": draft().model_dump()},
        )
        assert response.status_code == 409
        response = await client.post(
            "/admin/platform/access/policy-preview",
            json={"conditions": [{"claim": ["x"], "operator": "regex", "value": "["}]},
        )
        assert response.status_code == 422
        access.rebac.admin = False
        response = await client.post(
            "/admin/platform/access/policy-preview", json=draft().model_dump()
        )
        assert response.status_code == 403
        response = await client.put(
            "/admin/platform/access/policy",
            json={"expected_revision": 2, "policy": draft().model_dump()},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_pg_concurrent_policy_saves_one_winner(pg_access):
    import asyncio

    actor = user("accepted")
    results = await asyncio.gather(
        service.save_policy(pg_access, actor, draft("accepted", ["attribute"]), 1),
        service.save_policy(pg_access, actor, draft("other", ["attribute"]), 1),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, HTTPException)
            and result.detail == "platform_access_policy_conflict"
            for result in results
        )
        == 1
    )
    assert (await pg_access.state()).revision == 2


@pytest.mark.asyncio
async def test_preview_requires_verified_own_human_identity(access):
    for actor in [
        SimpleNamespace(uid=str(uuid4())),
        user().model_copy(update={"service_account": True}),
        user().model_copy(update={"roles": ["service_agent"]}),
    ]:
        with pytest.raises(HTTPException) as error:
            await service.preview_policy(access, cast(KeycloakUser, actor), draft())
        assert error.value.status_code == 403
        assert error.value.detail == "requires_own_credential"


@pytest.mark.asyncio
async def test_pg_locked_authority_has_bounded_unavailable_response(pg_access):
    import asyncio

    import sqlalchemy as sa

    async with pg_access.store.engine.begin() as connection:
        await connection.execute(
            sa.text("LOCK TABLE platform_access_settings IN ACCESS EXCLUSIVE MODE")
        )
        started = time.monotonic()
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(pg_access.admitted(user("accepted")), timeout=7)
        assert error.value.status_code == 503
        assert error.value.detail == "platform_access_unavailable"
        assert time.monotonic() - started < 7
    assert await pg_access.admitted(user("accepted"))


@pytest.mark.asyncio
async def test_pg_t0_matching_does_not_hold_policy_lock(pg_access, monkeypatch):
    import asyncio
    import threading

    actor = user("accepted")
    await pg_access.observe(actor)
    entered, release = threading.Event(), threading.Event()
    original = pg_access.observed_match

    def blocked_match(row, policy):
        entered.set()
        released = release.wait(timeout=4)
        assert released
        return original(row, policy)

    monkeypatch.setattr(pg_access, "observed_match", blocked_match)
    preview = asyncio.create_task(service.t0(pg_access))
    entered_in_time = await asyncio.to_thread(entered.wait, 2)
    assert entered_in_time
    try:
        changed = await asyncio.wait_for(
            service.save_policy(pg_access, actor, draft("accepted", ["attribute"]), 1),
            timeout=2,
        )
        assert changed.revision == 2
    finally:
        release.set()
        await asyncio.wait_for(preview, timeout=10)


@pytest.mark.asyncio
async def test_completed_t0_retry_reports_completion_despite_concurrent_rule_edit(
    access, monkeypatch
):
    import asyncio
    import threading

    actor = user("accepted")
    await access.observe(actor)
    first = await service.t0(access, actor)
    entered, release = threading.Event(), threading.Event()
    original = access.observed_match

    def blocked_match(row, policy):
        entered.set()
        released = release.wait(timeout=4)
        assert released
        return original(row, policy)

    monkeypatch.setattr(access, "observed_match", blocked_match)
    retry = asyncio.create_task(service.t0(access, actor))
    entered_in_time = await asyncio.to_thread(entered.wait, 2)
    assert entered_in_time
    try:
        await service.save_policy(access, actor, draft("accepted"), 1)
    finally:
        release.set()
    assert first.completed_at is not None
    assert (await retry).completed_at == first.completed_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_pg_live_policy_and_free_journey_with_cached_human_facts(pg_access):
    actor, newcomer = user("accepted"), user()
    newcomer.admission_claims[path_key(["other", "unit"])] = "preview-only"
    await pg_access.observe(actor)
    await service.set_filtering(pg_access, actor, True)
    second = PlatformAccess(
        PlatformAccessStore(pg_access.store.engine), pg_access.rebac
    )
    assert not await second.admitted(newcomer)
    await service.save_policy(pg_access, actor, draft("accepted", ["attribute"]), 1)
    assert not await second.admitted(newcomer)
    token = await service.generate_link(pg_access, "demo", user("accepted"))
    await service.accept_cgu(pg_access, newcomer, token, "v2", "v2")
    enrolled = await service.enroll(pg_access, newcomer, token, "v2")
    assert enrolled.admitted
    assert await second.admitted(cast(Principal, SimpleNamespace(uid=newcomer.uid)))
    await service.set_team(pg_access, actor, "demo", False, False)
    assert not await second.admitted(newcomer)
    assert not await second.admitted(cast(Principal, SimpleNamespace(uid=newcomer.uid)))
    await service.set_user(pg_access, actor, UUID(newcomer.uid), True)
    assert await second.admitted(newcomer)
    await service.set_user(pg_access, actor, UUID(newcomer.uid), False)
    assert not await second.admitted(newcomer)
    observed = await second.store.user(UUID(newcomer.uid))
    assert observed is not None and observed.admission_attribute is not None
    assert path_key(["other", "unit"]) not in observed.admission_attribute


@pytest.mark.asyncio
async def test_legacy_gate_blocks_activation_and_active_readers(access, monkeypatch):
    from fred_core.security.whitelist_access_control import access_control as legacy

    monkeypatch.setattr(legacy, "is_whitelist_active", lambda: True)
    actor = user("accepted")
    assert await access.admitted(actor)
    with pytest.raises(HTTPException) as conflict:
        await service.set_filtering(access, actor, True)
    assert conflict.value.detail == "platform_access_legacy_gate_conflict"
    assert not (await access.state()).filtering_enabled
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.filtering_enabled = True
    with pytest.raises(HTTPException) as unavailable:
        await access.admitted(actor)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_bulk_grants_are_atomic_preserve_provenance_and_revoke_independently(
    access,
):
    actor, first, second = user("accepted"), user(), user()
    await access.observe(first)
    await access.observe(second)
    async with access.store.mutation() as session:
        await access.store.add_exception(UUID(first.uid), actor.uid, "t0", session)
    await service.set_filtering(access, actor, True)
    unknown = uuid4()
    with pytest.raises(HTTPException) as missing:
        await service.grant_users(access, actor, [UUID(second.uid), unknown])
    assert missing.value.detail == "user_not_found"
    assert await access.store.exception(UUID(second.uid)) is None
    await service.grant_users(
        access, actor, [UUID(first.uid), UUID(second.uid), UUID(second.uid)]
    )
    assert (await access.store.exception(UUID(first.uid))).source == "t0"
    assert (await access.store.exception(UUID(second.uid))).source == "manual"
    assert await access.admitted(first) and await access.admitted(second)
    await service.set_user(access, actor, UUID(second.uid), False)
    assert not await access.admitted(second)
    assert await access.admitted(first)


@pytest.mark.asyncio
async def test_bulk_endpoint_bounds_unknown_users_and_fresh_admin_permission(access):
    from unittest.mock import AsyncMock

    actor, first, second = user("accepted"), user(), user()
    await access.observe(first)
    await access.observe(second)
    gate = AsyncMock()
    access.rebac.check_user_permission_or_raise = gate
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for payload in ([], [first.uid] * 101, ["invalid"]):
            response = await client.post(
                "/admin/platform/access/users", json={"user_ids": payload}
            )
            assert response.status_code == 422
        response = await client.post(
            "/admin/platform/access/users",
            json={"user_ids": [first.uid, str(uuid4())]},
        )
        assert response.status_code == 404
        assert await access.store.exception(UUID(first.uid)) is None
        response = await client.post(
            "/admin/platform/access/users",
            json={"user_ids": [first.uid, second.uid]},
        )
        assert response.status_code == 204
        assert (
            gate.call_args.kwargs["consistency_token"]
            == access.rebac.HIGHER_CONSISTENCY
        )
        gate.side_effect = HTTPException(403, "forbidden")
        third = user()
        await access.observe(third)
        response = await client.post(
            "/admin/platform/access/users", json={"user_ids": [third.uid]}
        )
        assert response.status_code == 403
        assert await access.store.exception(UUID(third.uid)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("free", [True, False])
async def test_member_removal_revokes_global_direct_cached_and_delegated_access(
    access, free
):
    actor, member = user("accepted"), user()
    await access.observe(member)
    await service.set_team(access, actor, "demo", not free, free)
    await service.set_filtering(access, actor, True)
    access.rebac.members[member.uid] = {"demo"}
    other_reader = PlatformAccess(
        PlatformAccessStore(access.store.engine), access.rebac
    )
    delegated = cast(Principal, SimpleNamespace(uid=member.uid))
    assert await access.admitted(member)
    assert await other_reader.admitted(delegated)
    access.rebac.members[member.uid].remove("demo")
    assert not await other_reader.admitted(member)
    assert not await access.admitted(delegated)
    assert await access.store.exception(UUID(member.uid)) is None
    await service.grant_users(access, actor, [UUID(member.uid)])
    assert await other_reader.admitted(member)
    assert await access.admitted(delegated)


@pytest.mark.asyncio
async def test_team_deletion_protects_admin_last_source_before_external_deletes(
    access, monkeypatch
):
    from unittest.mock import AsyncMock

    from control_plane_backend.teams.service import delete_team
    from fred_core.security.platform_access import access_control

    actor, accepted = user(), user("accepted")
    await access.observe(actor)
    access.rebac.members[actor.uid] = {"demo"}
    await service.set_team(access, accepted, "demo", False, True)
    await service.set_filtering(access, actor, True)
    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", access)
    remove_relations = AsyncMock()
    access.rebac.delete_all_relations_of_reference = remove_relations
    store = SimpleNamespace(
        get_by_team_id=AsyncMock(return_value=object()), delete=AsyncMock()
    )
    deps = SimpleNamespace(rebac=access.rebac, get_team_metadata_store=lambda: store)
    with pytest.raises(HTTPException) as lockout:
        await delete_team(actor, TeamId("demo"), cast(TeamServiceDependencies, deps))
    assert lockout.value.detail == "platform_access_actor_lockout"
    remove_relations.assert_not_awaited()
    store.delete.assert_not_awaited()
    await service.grant_users(access, accepted, [UUID(actor.uid)])
    await delete_team(actor, TeamId("demo"), cast(TeamServiceDependencies, deps))
    remove_relations.assert_awaited_once()
    store.delete.assert_awaited_once_with("demo")


@pytest.mark.asyncio
@pytest.mark.parametrize("self_leave", [False, True])
async def test_actual_full_member_removal_with_multiple_roles_revokes_other_reader(
    access, self_leave
):
    from control_plane_backend.scheduler.policies.policy_models import (
        ConversationPolicyCatalog,
    )
    from control_plane_backend.teams.service import remove_team_member
    from fred_core.security.rebac.rebac_engine import RebacEngine
    from tests.test_team_member_roles import _deps, _FakeRebac

    class RoleEngine(_FakeRebac):
        HIGHER_CONSISTENCY = RebacEngine.HIGHER_CONSISTENCY

        async def _has_permission_raw(self, subject, permission, resource, **kwargs):
            assert kwargs["consistency_token"] == self.HIGHER_CONSISTENCY
            return resource.id == "fredlab" and bool(self.roles.get(subject.id))

        async def has_team_memberships(self, uid, teams):
            return await RebacEngine.has_team_memberships(
                cast(RebacEngine, self), uid, teams
            )

    class EmptySessions:
        async def get_for_user(self, *args):
            return []

    actor, member = user("accepted"), user()
    rebac = RoleEngine(
        roles={
            actor.uid: {UserTeamRelation.TEAM_ADMIN},
            member.uid: set(UserTeamRelation),
        }
    )
    access.rebac = cast(RebacEngine, rebac)
    async with access.store.mutation() as session:
        session.add(
            TeamMetadataRow(
                id="fredlab", name="Free demonstration", platform_access_free=True
            )
        )
    await service.set_filtering(access, actor, True)
    other_reader = PlatformAccess(
        PlatformAccessStore(access.store.engine), cast(RebacEngine, rebac)
    )
    delegated = cast(Principal, SimpleNamespace(uid=member.uid))
    assert await access.admitted(member)
    assert await other_reader.admitted(delegated)
    deps = _deps(
        rebac,
        "fredlab",
        get_session_store=EmptySessions,
        get_purge_queue_store=object,
        get_policy_catalog=ConversationPolicyCatalog,
    )
    await remove_team_member(
        member if self_leave else actor, TeamId("fredlab"), member.uid, deps
    )
    assert not rebac.roles[member.uid]
    assert not await other_reader.admitted(member)
    assert not await access.admitted(delegated)
    assert await access.store.exception(UUID(member.uid)) is None


def test_own_claim_projection_preserves_exact_values_and_supported_paths():
    result = service.own_claims(
        {
            "profile": {"unit": "actual"},
            "a.b": ["one", "two"],
            "exp": 123,
            "enabled": True,
            "__proto__": "literal",
        }
    )
    assert result.claims["profile"] == {"unit": "actual"}
    assert result.claims["exp"] == 123 and result.claims["enabled"] is True
    assert ["profile", "unit"] in result.selectable_paths
    assert ["a.b"] in result.selectable_paths and [
        "__proto__"
    ] in result.selectable_paths
    assert ["exp"] not in result.selectable_paths
    assert not result.truncated


def test_own_claim_projection_is_bounded_and_omitted_fields_unselectable():
    import json

    payload: dict[str, object] = {f"field-{i}": "x" * 1024 for i in range(2000)}
    payload.update({"large": "x" * 1025, "array": ["x"] * 33})
    result = service.own_claims(payload)
    assert result.truncated
    assert len(json.dumps(result.claims, ensure_ascii=True)) < 65536
    assert "large" not in result.claims and "array" not in result.claims
    assert all(path[0] in result.claims for path in result.selectable_paths)


@pytest.mark.asyncio
async def test_own_claim_endpoint_requires_admin_own_verified_human_and_disables_caching(
    access, monkeypatch
):
    actor = user()

    def decode(token, *, verified_payload):
        assert token == "test-token"
        verified_payload.update({"profile": {"unit": "actual"}, "exp": 123})
        return actor

    import threading

    original_projection = service.own_claims

    def projection(payload):
        assert threading.current_thread() is not threading.main_thread()
        return original_projection(payload)

    monkeypatch.setattr(service, "own_claims", projection)
    monkeypatch.setattr(api, "decode_jwt", decode)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        response = await client.get("/admin/platform/access/own-claims")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["claims"]["profile"]["unit"] == "actual"
        access.rebac.admin = False
        response = await client.get("/admin/platform/access/own-claims")
        assert response.status_code == 403
        access.rebac.admin = True
        actor.service_account = True
        response = await client.get("/admin/platform/access/own-claims")
        assert response.status_code == 403
        assert "actual" not in response.text
        actor.service_account = False
        app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
            uid=actor.uid, roles=[]
        )
        response = await client.get("/admin/platform/access/own-claims")
        assert response.status_code == 403
        assert "actual" not in response.text


@pytest.mark.asyncio
async def test_free_link_history_openings_recovery_expiry_and_individual_revocation(
    access,
):
    from datetime import datetime, timedelta, timezone

    from control_plane_backend.platform_access.schemas import (
        CreatePlatformEnrollmentLink,
    )

    actor, newcomer = user("accepted"), user()
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(
        access, "demo", actor, CreatePlatformEnrollmentLink(note="Workshop")
    )
    page = await service.list_links(access, "demo", 0, 25)
    first = page.items[0]
    assert (
        first.note == "Workshop"
        and first.expires_at is None
        and first.status == "active"
    )
    assert token not in page.model_dump_json()
    revision = (await access.state()).revision
    await service.record_opening(access, token)
    assert (await service.list_links(access, "demo", 0, 25)).items[0].opening_count == 1
    await service.preview_link(access, newcomer, token, None)
    await service.enroll(access, newcomer, token, None)
    assert (await service.list_links(access, "demo", 0, 25)).items[0].opening_count == 1
    assert await service.reveal_link(access, "demo", first.id) == token
    await service.record_opening(access, token)
    assert (await service.list_links(access, "demo", 0, 25)).items[0].opening_count == 2
    assert (await access.state()).revision == revision
    later = await service.generate_link(
        access,
        "demo",
        actor,
        CreatePlatformEnrollmentLink(
            note="Later",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    history = await service.list_links(access, "demo", 0, 1)
    assert history.total == 2 and len(history.items) == 1
    later_id = history.items[0].id
    await service.set_team(access, actor, "demo", False, False)
    assert all(
        item.status == "suspended"
        for item in (await service.list_links(access, "demo", 0, 25)).items
    )
    with pytest.raises(HTTPException):
        await service.record_opening(access, token)
    await service.revoke_link(access, "demo", first.id)
    await service.revoke_link(access, "demo", first.id)
    await service.set_team(access, actor, "demo", False, True)
    with pytest.raises(HTTPException):
        await service.enroll(access, user(), token, None)
    await service.preview_link(access, newcomer, later, None)
    async with access.store.mutation() as session:
        row = await session.get(PlatformAccessLinkRow, later_id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await service.list_links(access, "demo", 0, 25)).items[
        0
    ].status == "expired"
    for operation in (
        lambda: service.preview_link(access, newcomer, later, None),
        lambda: service.enroll(access, newcomer, later, None),
        lambda: service.accept_cgu(access, newcomer, later, "v1", "v1"),
        lambda: service.record_opening(access, later),
    ):
        with pytest.raises(HTTPException):
            await operation()
    with pytest.raises(HTTPException):
        await service.reveal_link(access, "other-team", first.id)


def test_link_creation_rejects_past_naive_expiry_and_oversized_note():
    from datetime import datetime, timedelta, timezone

    from control_plane_backend.platform_access.schemas import (
        CreatePlatformEnrollmentLink,
    )
    from pydantic import ValidationError

    for body in (
        {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
        {"expires_at": datetime.now() + timedelta(days=1)},
        {"note": "x" * 513},
        {"created_by": "another-person"},
    ):
        with pytest.raises(ValidationError):
            CreatePlatformEnrollmentLink.model_validate(body)


@pytest.mark.asyncio
async def test_link_admin_history_and_tokens_are_guarded(access):
    actor = user("accepted")
    await access.observe(actor)
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo", actor)
    link_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        access.rebac.admin = False
        for method, path in (
            ("GET", "/admin/platform/access/teams/demo/enrollment-links"),
            (
                "POST",
                f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/reveal",
            ),
            ("DELETE", f"/admin/platform/access/teams/demo/enrollment-links/{link_id}"),
        ):
            assert (await client.request(method, path)).status_code == 403
        access.rebac.admin = True
        history = await client.get("/admin/platform/access/teams/demo/enrollment-links")
        assert token not in history.text
        revealed = await client.post(
            f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/reveal"
        )
        assert revealed.json() == {"token": token}
        assert revealed.headers["cache-control"] == "no-store"
        actor.service_account = True
        assert (
            await client.post(
                f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/reveal"
            )
        ).status_code == 403
        assert (
            await client.post(
                "/admin/platform/access/teams/demo/enrollment-link", json={}
            )
        ).status_code == 403


@pytest.mark.asyncio
async def test_pg_concurrent_openings_and_revocation_are_serialized(pg_access):
    import asyncio

    token = await service.generate_link(pg_access, "demo", user("accepted"))
    link_id = (await service.list_links(pg_access, "demo", 0, 25)).items[0].id
    await asyncio.gather(*(service.record_opening(pg_access, token) for _ in range(4)))
    assert (await service.list_links(pg_access, "demo", 0, 25)).items[
        0
    ].opening_count == 4
    async with pg_access.store.mutation() as session:
        link = await session.get(PlatformAccessLinkRow, link_id)
        from datetime import datetime, timezone

        link.revoked_at = datetime.now(timezone.utc)
        await session.flush()
        enrolling = asyncio.create_task(service.enroll(pg_access, user(), token, None))
        await asyncio.sleep(0.05)
        assert not enrolling.done()
    with pytest.raises(HTTPException):
        await asyncio.wait_for(enrolling, timeout=5)
    assert not pg_access.rebac.writes


@pytest.mark.asyncio
async def test_block_policy_preserves_exceptions_and_live_team_revocation(access):
    actor, blocked, other = user("other"), user("accepted"), user("other")
    policy = draft().model_copy(update={"mode": "block"})
    await service.save_policy(access, actor, policy, 1)
    await service.set_filtering(access, actor, True)
    assert not await access.admitted(blocked)
    assert await access.admitted(other)
    assert (await service.preview_policy(access, blocked, policy)).matched
    assert not (await service.preview_policy(access, blocked, policy)).admitted
    await service.set_user(access, actor, UUID(blocked.uid), True)
    assert await access.admitted(blocked)
    await service.set_user(access, actor, UUID(blocked.uid), False)
    assert not await access.admitted(blocked)
    await service.set_team(access, actor, "demo", False, True)
    access.rebac.members[blocked.uid] = {"demo"}
    assert await access.admitted(blocked)
    access.rebac.members[blocked.uid].clear()
    assert not await access.admitted(blocked)
    assert (await access.state()).policy["mode"] == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", 17, [], {"nested": "value"}])
async def test_block_policy_admits_verified_nonmatching_unusable_claims(access, value):
    policy = draft().model_copy(update={"mode": "block"})
    actor = user("other")
    await service.save_policy(access, actor, policy, 1)
    person = user()
    person.admission_claims, person.admission_invalid_claims = extract_claims(
        {} if value is None else {"profile": {"attribute": value}}
    )
    assert await access.eligible(person)
    assert (await service.preview_policy(access, person, policy)).admitted
    delegated = cast(Principal, SimpleNamespace(uid=person.uid))
    assert await access.eligible(delegated)
    async with access.store.mutation() as session:
        row = await session.get(UserRow, UUID(person.uid))
        row.admission_expires_at = time.time() - 1
    assert not await access.eligible(delegated)


@pytest.mark.asyncio
async def test_block_policy_requires_selected_delegated_evidence_and_rejects_lockout(
    access,
):
    actor = user("other")
    await access.observe(actor)
    delegated = cast(Principal, SimpleNamespace(uid=actor.uid))
    policy = draft(claim=["new"]).model_copy(update={"mode": "block"})
    await service.save_policy(access, actor, policy, 1)
    assert not await access.eligible(delegated)
    assert await access.eligible(actor)
    assert await access.eligible(delegated)
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException, match="platform_access_actor_lockout"):
        await service.save_policy(
            access, actor, draft("other").model_copy(update={"mode": "block"}), 2
        )


def test_policy_modes_keep_literal_match_distinct_and_timeout_fail_closed():
    from fred_core.security.platform_access.rules import Evaluation, allows, evaluate

    allow = draft()
    assert (
        PlatformAccessPolicy.model_validate(
            {"conditions": allow.model_dump()["conditions"]}
        ).mode
        == "allow"
    )
    block = allow.model_copy(update={"mode": "block"})
    matched = evaluate(block, extract_claims({"profile": {"attribute": "accepted"}})[0])
    assert matched.matched and not allows(block, matched)
    assert allows(allow, matched)
    assert not allows(block, Evaluation(False, ["timeout"]))
    assert not allows(None, Evaluation(False, []))


@pytest.mark.asyncio
async def test_block_policy_never_admits_uninspected_truncated_claims(access):
    policy = draft().model_copy(update={"mode": "block"})
    actor, person = user("other"), user("accepted")
    await service.save_policy(access, actor, policy, 1)
    payload: dict[str, object] = {str(index): "value" for index in range(256)}
    payload["profile"] = {"attribute": "accepted"}
    person.admission_claims, person.admission_invalid_claims = extract_claims(payload)
    assert not await access.eligible(person)
    assert not await access.eligible(cast(Principal, SimpleNamespace(uid=person.uid)))
    preview = await service.preview_policy(access, person, policy)
    assert preview.conditions == ["unavailable"] and not preview.admitted
    row = await access.store.user(UUID(person.uid))
    assert path_key(["profile", "attribute"]) not in row.admission_attribute
