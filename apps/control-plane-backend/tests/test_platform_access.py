# SPDX-License-Identifier: Apache-2.0
import time
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.platform_access import api, service
from fastapi import FastAPI, HTTPException
from fred_core.security.models import Resource
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.platform_access.models import (
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import RebacReference, RelationType
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from fred_pod.security.structure import KeycloakUser, PlatformAccessConfiguration
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl
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
            PlatformAccessSettingsRow,
            PlatformAccessUserRow,
        ):
            await connection.run_sync(cast(Table, model.__table__).create)
    config = PlatformAccessConfiguration(
        enabled=True,
        jwt_claim=["profile", "attribute"],
        accepted_regex="accepted",
        supportLink=AnyHttpUrl("https://support.example.org"),
    )
    value = PlatformAccess(config, PlatformAccessStore(engine), MembershipEngine())
    async with value.store.mutation() as session:
        session.add(
            PlatformAccessSettingsRow(
                id=1, policy_fingerprint=value.fingerprint, filtering_enabled=False
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
        admission_attribute=attribute,
        admission_issued_at=time.time() - 1,
        admission_expires_at=time.time() + 300,
    )


@pytest.mark.asyncio
async def test_t0_once_and_deleted_entries_never_return(access):
    actor, existing, matching = user(), user(), user("accepted")
    for person in (actor, existing, matching):
        await access.store.observe(person, access.path_fingerprint)
    preview = await service.t0(access)
    assert (preview.candidates, preview.matching, preview.completed_at) == (2, 1, None)
    result = await service.t0(access, actor)
    assert result.completed_at
    assert (await access.store.exception(UUID(existing.uid))).source == "t0"
    assert await access.store.exception(UUID(matching.uid)) is None
    await service.set_user(access, actor, UUID(existing.uid), False)
    later = user()
    await access.store.observe(later, access.path_fingerprint)
    again = await service.t0(access, actor)
    assert again.completed_at == result.completed_at.replace(tzinfo=None)
    assert await access.store.exception(UUID(existing.uid)) is None
    assert await access.store.exception(UUID(later.uid)) is None


@pytest.mark.asyncio
async def test_filter_and_exception_mutations_preserve_acting_admin(access):
    actor = user()
    await access.store.observe(actor, access.path_fingerprint)
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
    await access.store.observe(actor, access.path_fingerprint)
    await service.set_team(access, actor, "demo", True, False)
    access.rebac.members[actor.uid] = {"demo"}
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException):
        await service.set_team(access, actor, "demo", False, False)
    assert await access.admitted(actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["v1", "2026-10"])
async def test_free_link_rotation_revocation_and_private_enrollment(access, version):
    actor, newcomer = user("accepted"), user()
    await access.store.observe(actor, access.path_fingerprint)
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo")
    assert len(token) == 43
    team = (await access.store.teams())[0]
    assert token != team.enrollment_token_hash
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
    assert (await service.enroll(access, newcomer, token, version)).admitted
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
    replacement = await service.generate_link(access, "demo")
    with pytest.raises(HTTPException):
        await service.enroll(access, user(), token, None)
    assert await access.admitted(newcomer)
    await service.set_team(access, actor, "demo", False, False)
    assert not await access.admitted(newcomer)
    await service.set_team(access, actor, "demo", False, True)
    with pytest.raises(HTTPException):
        await service.enroll(access, user(), replacement, None)


@pytest.mark.asyncio
async def test_failed_membership_write_can_retry_without_granting_admin(access):
    actor, newcomer = user(), user()
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo")
    access.rebac.write_failure = True
    with pytest.raises(RuntimeError):
        await service.enroll(access, newcomer, token, None)
    access.rebac.write_failure = False
    await service.enroll(access, newcomer, token, None)
    assert len(access.rebac.writes) == 1
    assert access.rebac.writes[0].subject.id == newcomer.uid


@pytest.mark.asyncio
async def test_personal_team_and_nonfree_link_are_refused(access):
    with pytest.raises(HTTPException):
        await service.set_team(access, user(), "personal-user", True, True)
    with pytest.raises(HTTPException):
        await service.generate_link(access, "demo")


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
    app.dependency_overrides[api.get_current_user] = lambda: user()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/admin/platform/access",
            "/admin/platform/access/users",
            "/admin/platform/access/teams",
            "/admin/platform/access/t0-preview",
        ):
            assert (await client.get(path)).status_code == 403
        assert (
            await client.post("/admin/platform/access/t0-import")
        ).status_code == 403
        assert (
            await client.patch(
                "/admin/platform/access", json={"filtering_enabled": True}
            )
        ).status_code == 403
        target = str(uuid4())
        assert (
            await client.put(f"/admin/platform/access/users/{target}")
        ).status_code == 403
        assert (
            await client.delete(f"/admin/platform/access/users/{target}")
        ).status_code == 403
        assert (
            await client.patch(
                "/admin/platform/access/teams/demo",
                json={"allowed": True, "free": True},
            )
        ).status_code == 403
        assert (
            await client.post("/admin/platform/access/teams/demo/enrollment-link")
        ).status_code == 403
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
                PlatformAccessSettingsRow,
                PlatformAccessUserRow,
            ):
                await connection.run_sync(cast(Table, model.__table__).create)
        value = PlatformAccess(
            PlatformAccessConfiguration(
                enabled=True,
                jwt_claim=["attribute"],
                accepted_regex="accepted",
                supportLink=AnyHttpUrl("https://support.example.org"),
            ),
            PlatformAccessStore(engine),
            MembershipEngine(),
        )
        async with value.store.mutation() as session:
            session.add(
                PlatformAccessSettingsRow(
                    id=1, policy_fingerprint=value.fingerprint, filtering_enabled=False
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
    await pg_access.store.observe(existing, pg_access.path_fingerprint)
    results = await asyncio.gather(
        service.t0(pg_access, actor), service.t0(pg_access, actor)
    )
    assert results[0].completed_at == results[1].completed_at
    await service.set_user(pg_access, actor, UUID(existing.uid), False)
    later = user()
    await pg_access.store.observe(later, pg_access.path_fingerprint)
    await service.t0(pg_access, actor)
    assert await pg_access.store.exception(UUID(existing.uid)) is None
    assert await pg_access.store.exception(UUID(later.uid)) is None


@pytest.mark.asyncio
async def test_pg_enrollment_serializes_free_revocation(pg_access, monkeypatch):
    import asyncio

    actor, newcomer = user("accepted"), user()
    token = await service.generate_link(pg_access, "demo")
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
        pg_access.config, PlatformAccessStore(pg_access.store.engine), pg_access.rebac
    )
    assert not await second.admitted(newcomer)
    with pytest.raises(HTTPException):
        await service.enroll(second, user(), token, None)


@pytest.mark.asyncio
async def test_pg_link_disabled_before_locked_enrollment_refuses(pg_access):
    import asyncio

    token = await service.generate_link(pg_access, "demo")
    newcomer = user()
    await pg_access.store.observe(newcomer, pg_access.path_fingerprint)
    async with pg_access.store.mutation() as session:
        team = await pg_access.store.team("demo", session)
        team.platform_access_free = False
        team.enrollment_token_hash = None
        await session.flush()
        enrolling = asyncio.create_task(
            service.enroll(pg_access, newcomer, token, None)
        )
        await asyncio.sleep(0.05)
        assert not enrolling.done()
    with pytest.raises(HTTPException):
        await enrolling
    assert pg_access.rebac.writes == []


@pytest.mark.asyncio
async def test_pg_startup_authority_missing_schema_and_policy_mismatch(
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
    security = SecurityConfiguration.model_construct(platform_access=pg_access.config)
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
    security.platform_access = pg_access.config.model_copy(
        update={"accepted_regex": "different"}
    )
    with pytest.raises(HTTPException, match="platform_access_unavailable"):
        await access_control.initialize_platform_access(security, engine, rebac)
    assert (await pg_access.state()).policy_fingerprint == pg_access.fingerprint
    async with engine.begin() as connection:
        await connection.execute(sa.text("DROP TABLE platform_access_users"))
    with pytest.raises(RuntimeError, match="platform_access_users"):
        await access_control.initialize_platform_access(
            security, engine, rebac, authority=True
        )
