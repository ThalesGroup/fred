# SPDX-License-Identifier: Apache-2.0
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.platform_access import api, service
from control_plane_backend.platform_access.directory import PlatformAccessDirectory
from control_plane_backend.platform_access.schemas import (
    PlatformT0Preview,
    PlatformT0RefreshMode,
    RefreshPlatformT0,
)
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.users.dependencies import (
    UserServiceDependencies,
    get_user_service_dependencies,
)
from fastapi import FastAPI, HTTPException
from fred_core.common import TeamId
from fred_core.security.models import Resource
from fred_core.security.platform_access.access_control import (
    PlatformAccess,
    get_platform_access,
)
from fred_core.security.platform_access.models import (
    PlatformAccessLinkJoinerRow,
    PlatformAccessLinkRow,
    PlatformAccessRemovalRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import (
    extract_claims,
    path_key,
)
from fred_core.security.platform_access.store import PlatformAccessStore
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import (
    OrganizationPermission,
    RebacReference,
    RelationType,
)
from fred_core.teams.metadata_store import TEAM_DESCRIPTION_PLACEHOLDER
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
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import create_async_engine


class MembershipEngine(NoopRebacEngine):
    def __init__(self):
        super().__init__()
        self.members: dict[str, set[str]] = {}
        self.admin = True
        self.admins: set[str] = set()
        self.permission_checks: list[OrganizationPermission] = []
        self.writes = []
        self.write_failure = False

    async def _lookup_resources_raw(self, subject, permission, resource_type, **kwargs):
        return [
            RebacReference(Resource.TEAM, team)
            for team in self.members.get(subject.id, set())
        ]

    async def _has_permission_raw(self, subject, permission, resource, **kwargs):
        if permission == OrganizationPermission.CAN_MANAGE_PLATFORM_ACCESS:
            return subject.id in self.admins
        return resource.id in self.members.get(subject.id, set())

    async def check_user_permission_or_raise(self, *args, **kwargs):
        self.permission_checks.append(args[1])
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

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        for model in (
            UserRow,
            TeamMetadataRow,
            PlatformAccessLinkRow,
            PlatformAccessRemovalRow,
            PlatformAccessLinkJoinerRow,
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
                description=TEAM_DESCRIPTION_PLACEHOLDER,
                id="demo",
                name="Demonstration",
                joining_mode="invite_only",
                visibility="private",
            )
        )
    yield value
    await engine.dispose()


async def free_joiner(access, uid: str, team_id: str = "demo") -> None:
    """Record a Free-link join: the only evidence of a Free admission source."""
    link_id = uuid4()
    async with access.store.mutation() as session:
        session.add(
            PlatformAccessLinkRow(
                id=link_id,
                team_id=team_id,
                token_hash=uuid4().hex + uuid4().hex,
                created_by=uid,
                created_at=datetime.now(timezone.utc),
                opening_count=0,
            )
        )
        await session.flush()
        session.add(
            PlatformAccessLinkJoinerRow(
                link_id=link_id,
                user_id=UUID(uid),
                joined_at=datetime.now(timezone.utc),
            )
        )


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


def local_user_deps() -> UserServiceDependencies:
    return cast(
        UserServiceDependencies,
        SimpleNamespace(
            configuration=SimpleNamespace(
                security=SimpleNamespace(user_directory="local")
            ),
            create_keycloak_admin_client=lambda: None,
        ),
    )


class FakeDirectoryAdmin:
    def __init__(self, users):
        self.users = {item["id"]: item for item in users}
        self.calls = []
        self.get_calls = []

    async def a_get_users(self, params):
        self.calls.append(params)
        for field in ("username", "email"):
            if field in params:
                value = str(params[field]).casefold()
                matches = [
                    item
                    for item in self.users.values()
                    if str(item.get(field, "")).casefold() == value
                ]
                return matches[params["first"] : params["first"] + params["max"]]
        query = str(params.get("search", "")).casefold()
        matches = [
            item
            for item in self.users.values()
            if query
            in " ".join(
                str(item.get(field, ""))
                for field in ("username", "firstName", "lastName", "email")
            ).casefold()
        ]
        return matches[params["first"] : params["first"] + params["max"]]

    async def a_users_count(self, params=None):
        params = params or {}
        query = str(params.get("search", "")).casefold()
        return sum(
            query
            in " ".join(
                str(item.get(field, ""))
                for field in ("username", "firstName", "lastName", "email")
            ).casefold()
            for item in self.users.values()
        )

    async def a_get_user(self, user_id):
        self.get_calls.append(user_id)
        return self.users.get(user_id)


def keycloak_directory(admin):
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            security=SimpleNamespace(user_directory="keycloak")
        ),
        create_keycloak_admin_client=lambda: admin,
    )
    return PlatformAccessDirectory(cast(UserServiceDependencies, deps))


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
async def test_keycloak_grant_resolves_profile_without_prior_fred_row(access):
    actor = user()
    uid = uuid4()
    missing = uuid4()
    admin = FakeDirectoryAdmin(
        [
            {
                "id": str(uid),
                "username": "julien-bouchet",
                "firstName": "Julien",
                "lastName": "BOUCHET",
            }
        ]
    )
    directory = keycloak_directory(admin)

    with pytest.raises(HTTPException, match="user_not_found"):
        await service.grant_users(access, actor, [uid, missing], directory)
    assert await access.store.user(uid) is None

    assert await service.grant_users(access, actor, [uid], directory) == 1
    assert (await access.store.user(uid)).username is None
    assert (
        await service.users_page(
            access, 0, 25, "", directory=PlatformAccessDirectory(local_user_deps())
        )
    ).total == 0
    page = await service.users_page(access, 0, 25, "", True, directory)
    assert page.total == 1
    assert (
        page.items[0].username,
        page.items[0].first_name,
        page.items[0].last_name,
    ) == ("julien-bouchet", "Julien", "BOUCHET")

    admin.users[str(uid)]["firstName"] = "Jules"
    page = await service.users_page(access, 0, 25, "Jules", True, directory)
    assert page.total == 1 and page.items[0].first_name == "Jules"

    del admin.users[str(uid)]
    page = await service.users_page(access, 0, 25, "", True, directory)
    assert page.items[0].username == str(uid)
    by_id = await service.users_page(access, 0, 25, str(uid), True, directory)
    assert by_id.total == 1 and by_id.items[0].username == str(uid)
    assert [source.kind for source in page.items[0].sources] == ["manual"]
    await service.set_user(access, actor, uid, False, directory)
    assert await access.store.exception(uid) is None

    second = uuid4()
    admin.users[str(second)] = {"id": str(second), "username": "new-account"}
    await service.set_user(access, actor, second, True, directory)
    assert await access.store.exception(second) is not None


@pytest.mark.asyncio
async def test_keycloak_t0_imports_directory_humans_not_fred_only_rows(access):
    actor = user()
    federated, created, technical = uuid4(), uuid4(), uuid4()
    admin = FakeDirectoryAdmin(
        [
            {"id": str(federated), "username": "federated", "firstName": "Fed"},
            {"id": str(created), "username": "created-in-keycloak"},
            {"id": str(uuid4()), "username": "service-account-test"},
            {"id": "f:provider:unimported", "username": "not-yet-imported"},
        ]
    )
    directory = keycloak_directory(admin)
    async with access.store.mutation() as session:
        session.add(UserRow(id=technical))

    preview = await service.t0(access, directory=directory)
    assert (preview.candidates, preview.matching) == (2, 0)
    result, count = await service.import_t0(access, actor, directory)
    assert result.completed_at is not None and count == 2
    assert await access.store.exception(federated) is not None
    assert await access.store.exception(created) is not None
    assert (await access.store.user(created)).username is None
    assert await access.store.exception(technical) is None
    reviewed = await service.activation_preview(access, directory)
    assert {item.user_id for item in reviewed.users} == {
        str(federated),
        str(created),
    }


@pytest.mark.asyncio
async def test_keycloak_directory_paginates_and_fails_when_unavailable(access):
    admin = FakeDirectoryAdmin(
        [
            {"id": str(UUID(int=index + 1)), "username": f"person-{index}"}
            for index in range(205)
        ]
    )
    directory = keycloak_directory(admin)
    assert len(await directory.search()) == 205
    assert len(await directory.search("person-1")) == 111
    admin.calls.clear()
    page = await service.users_page(access, 0, 25, "person-1", directory=directory)
    assert page.total == 111 and len(page.items) == 25
    assert len(admin.calls) == 1
    preview = await service.t0(access, directory=directory)
    assert (preview.candidates, preview.matching) == (205, 0)
    imported, count = await service.import_t0(access, user(), directory)
    assert count == 205 and imported.completed_at is not None
    searched = await service.users_page(access, 0, 25, "person-1", True, directory)
    assert searched.total == 111 and len(searched.items) == 25
    assert admin.get_calls == []
    admin.calls.clear()
    assert (await service.t0(access, directory=directory)).completed_at is not None
    assert admin.calls == []

    class UnavailableAdmin:
        async def a_users_count(self, _params=None):
            raise RuntimeError("directory down")

        async def a_get_users(self, _params):
            raise RuntimeError("directory down")

        async def a_get_user(self, _user_id):
            raise RuntimeError("directory down")

    unavailable = keycloak_directory(UnavailableAdmin())
    with pytest.raises(HTTPException, match="platform_access_directory_unavailable"):
        await unavailable.search("person")
    with pytest.raises(HTTPException, match="platform_access_directory_unavailable"):
        await unavailable.by_ids([str(uuid4())])


@pytest.mark.asyncio
async def test_keycloak_add_search_counts_only_selectable_people_and_bounds_broad_queries():
    admin = FakeDirectoryAdmin(
        [
            {"id": str(uuid4()), "username": "user-human"},
            {"id": str(uuid4()), "username": "service-account-user"},
            {"id": "f:provider:unimported", "username": "user-external"},
        ]
    )
    directory = keycloak_directory(admin)
    page, total = await directory.search_page("user", 0, 25)
    assert total == 1 and [person.username for person in page] == ["user-human"]
    assert await directory.search_page("user", 1, 25) == ([], 1)

    large = FakeDirectoryAdmin(
        [
            {"id": str(UUID(int=index + 1)), "username": f"person-{index}"}
            for index in range(1001)
        ]
    )
    with pytest.raises(HTTPException) as error:
        await keycloak_directory(large).search_page("person", 0, 25)
    assert error.value.status_code == 422
    assert [call.get("exact") for call in large.calls] == [True, True]

    admin_id = uuid4()
    exact = FakeDirectoryAdmin(
        [
            {
                "id": str(UUID(int=index + 1)),
                "username": f"person-{index}",
                "email": f"admin-{index}@example.org",
            }
            for index in range(1001)
        ]
        + [{"id": str(admin_id), "username": "admin"}]
    )
    directory = keycloak_directory(exact)
    page, total = await directory.search_page("admin", 0, 25)
    assert total == 1 and page[0].id == str(admin_id)
    page, total = await directory.search_page(str(admin_id), 0, 1)
    assert total == 1 and page[0].username == "admin"


@pytest.mark.asyncio
async def test_local_directory_rejects_nonlocal_and_profileless_identities(access):
    actor = user()
    unknown = uuid4()
    profileless, local_id = uuid4(), uuid4()
    async with access.store.mutation() as session:
        session.add(UserRow(id=profileless))
        session.add(UserRow(id=local_id, username="local-person"))
    directory = PlatformAccessDirectory(local_user_deps())

    with pytest.raises(HTTPException, match="user_not_found"):
        await service.grant_users(access, actor, [unknown], directory)
    with pytest.raises(HTTPException, match="user_not_found"):
        await service.grant_users(access, actor, [profileless], directory)
    assert (await service.users_page(access, 0, 25, "", directory=directory)).total == 1
    by_id = await service.users_page(access, 0, 1, str(local_id), directory=directory)
    assert by_id.total == 1 and by_id.items[0].username == "local-person"
    assert (await service.t0(access, directory=directory)).candidates == 1


@pytest.mark.asyncio
async def test_t0_audit_reports_actual_import_once(access, monkeypatch):
    actor, candidate, matching = user(), user(), user("accepted")
    for person in (actor, candidate, matching):
        await access.observe(person)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        api, "emit_audit_log", lambda name, **fields: events.append((name, fields))
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/admin/platform/access/t0-import")
        later = user()
        await access.observe(later)
        retry = await client.post("/admin/platform/access/t0-import")
    assert first.status_code == retry.status_code == 200
    assert len(events) == 1
    assert events[0][0] == "platform.access.t0.imported"
    assert events[0][1]["actor_uid"] == actor.uid
    assert events[0][1]["candidates"] == 2
    assert events[0][1]["matching"] == 1
    assert events[0][1]["imported_count"] == 2


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
async def test_disabling_filtering_preserves_configuration_for_reactivation(access):
    actor, outsider = user(), user()
    await access.observe(actor)
    await service.set_user(access, actor, UUID(actor.uid), True)
    await service.set_team(access, actor, "demo", True, True)
    token = await service.generate_link(access, "demo", actor)
    original = await access.state()
    await service.set_filtering(access, actor, True)
    assert not await access.admitted(outsider)

    disabled = await service.set_filtering(access, actor, False)
    assert await access.admitted(outsider)
    assert disabled.policy == access.policy(original)
    assert disabled.revision == original.revision
    assert await access.store.exception(UUID(actor.uid)) is not None
    assert (await access.store.teams())[0].platform_access_free
    assert (await service.list_links(access, "demo", 0, 25)).total == 1
    assert (
        await service.preview_link(access, outsider, token, None)
    ).team_name == "Demonstration"

    await service.set_filtering(access, actor, True)
    assert not await access.admitted(outsider)


@pytest.mark.asyncio
async def test_live_platform_admin_is_admitted_and_visible_in_preview(access):
    actor = user()
    await access.observe(actor)
    access.rebac.admins.add(actor.uid)
    await service.set_filtering(access, actor, True)
    assert await access.admitted(actor)
    assert await access.admitted(cast(Principal, SimpleNamespace(uid=actor.uid)))
    preview = await service.activation_preview(access)
    entry = next(item for item in preview.users if item.user_id == actor.uid)
    assert entry.outcome == "allowed"
    assert any(source.kind == "admin" for source in entry.sources)
    access.rebac.admins.remove(actor.uid)
    assert not await access.admitted(actor)
    assert not await access.admitted(cast(Principal, SimpleNamespace(uid=actor.uid)))


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
    assert enrolled.admitted and enrolled.team_id == "demo"
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
    link_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    assert (await service.list_link_joiners(access, "demo", link_id, 0, 25)).total == 0
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
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
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
    assert set(access.rebac.permission_checks) == {
        OrganizationPermission.CAN_MANAGE_PLATFORM_ACCESS
    }


@pytest.mark.asyncio
async def test_denied_self_status_does_not_provision_team_or_directory(access):
    person = user()
    actor = user("accepted")
    await service.set_filtering(access, actor, True)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
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
                PlatformAccessRemovalRow,
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
                TeamMetadataRow(
                    description=TEAM_DESCRIPTION_PLACEHOLDER,
                    id="demo",
                    name="Demo",
                    platform_access_free=True,
                )
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
async def test_unseeded_policy_supports_explicit_exception_only_activation(access):
    actor = user()
    async with access.store.mutation() as session:
        state = await access.store.settings(session)
        state.policy, state.revision = None, 0
    await access.observe(actor)
    with pytest.raises(HTTPException, match="platform_access_policy_required"):
        await service.set_filtering(access, actor, True)
    await service.set_user(access, actor, UUID(actor.uid), True)
    assert (
        await service.state_view(access, await access.state())
    ).has_admission_sources
    await service.set_filtering(access, actor, True)
    assert (await access.state()).policy is None
    assert not await access.admitted(user())
    assert await access.admitted(actor)


@pytest.mark.asyncio
async def test_rule_endpoints_permissions_validation_and_retired_catalog(access):
    actor = user("accepted")
    await access.observe(actor)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
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

    actor = user("accepted")
    await access.observe(actor)
    first = await service.t0(access, actor)

    def unexpected_match(*_args):
        raise AssertionError("completed import scanned")

    monkeypatch.setattr(access, "observed_match", unexpected_match)
    retry = asyncio.create_task(service.t0(access, actor))
    await service.save_policy(access, actor, draft("accepted"), 1)
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
async def test_bulk_endpoint_bounds_unknown_users_and_fresh_admin_permission(
    access, monkeypatch
):
    from unittest.mock import AsyncMock

    actor, first, second = user("accepted"), user(), user()
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        api,
        "emit_audit_log",
        lambda name, **fields: events.append((name, fields)),
    )
    await access.observe(first)
    await access.observe(second)
    gate = AsyncMock()
    access.rebac.check_user_permission_or_raise = gate
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for payload in ([], ["invalid"]):
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
        assert events == []
        async with access.store.mutation() as session:
            await access.state(session)
            await access.store.add_exception(UUID(first.uid), actor.uid, "t0", session)
        response = await client.post(
            "/admin/platform/access/users",
            json={"user_ids": [first.uid] * 101 + [second.uid]},
        )
        assert response.status_code == 204
        summary = [
            fields for name, fields in events if name == "platform.access.users.granted"
        ]
        assert len(summary) == 1
        assert summary[0] == {
            "actor_uid": actor.uid,
            "count": 2,
            "granted_count": 1,
        }
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
        assert len(events) == 1


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
    if free:
        await free_joiner(access, member.uid)
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
    await free_joiner(access, actor.uid)
    await service.set_filtering(access, actor, True)
    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", access)
    remove_relations = AsyncMock()
    access.rebac.delete_all_relations_of_reference = remove_relations
    store = SimpleNamespace(
        get_by_team_id=AsyncMock(return_value=object()), delete=AsyncMock()
    )
    deps = SimpleNamespace(
        rebac=access.rebac,
        get_team_metadata_store=lambda: store,
        get_agent_instance_store=None,
    )
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
                description=TEAM_DESCRIPTION_PLACEHOLDER,
                id="fredlab",
                name="Free demonstration",
                platform_access_free=True,
            )
        )
    await free_joiner(access, member.uid, "fredlab")
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
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
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
    await service.record_opening(access, token, newcomer)
    assert (await service.list_links(access, "demo", 0, 25)).items[0].opening_count == 1
    await service.preview_link(access, newcomer, token, None)
    await service.enroll(access, newcomer, token, None)
    assert (await service.list_links(access, "demo", 0, 25)).items[0].opening_count == 1
    assert await service.reveal_link(access, "demo", first.id) == token
    await service.record_opening(access, token, newcomer)
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
        await service.record_opening(access, token, newcomer)
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
        lambda: service.record_opening(access, later, newcomer),
    ):
        with pytest.raises(HTTPException):
            await operation()
    with pytest.raises(HTTPException):
        await service.reveal_link(access, "other-team", first.id)


@pytest.mark.asyncio
async def test_free_link_joiners_follow_successful_enrollment_and_cleanup(
    access, monkeypatch
):
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        service, "emit_audit_log", lambda name, **fields: events.append((name, fields))
    )
    actor = user("accepted")
    first = user().model_copy(
        update={"username": "first", "first_name": "First", "last_name": "Joiner"}
    )
    second = user().model_copy(
        update={"username": "second", "first_name": "Second", "last_name": "Joiner"}
    )
    await service.set_team(access, actor, "demo", False, True)
    first_token = await service.generate_link(access, "demo", actor)
    first_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    second_token = await service.generate_link(access, "demo", actor)
    second_id = (await service.list_links(access, "demo", 0, 25)).items[0].id

    await service.preview_link(access, first, first_token, None)
    await service.record_opening(access, first_token, first)
    assert (await service.list_link_joiners(access, "demo", first_id, 0, 25)).total == 0
    await service.enroll(access, first, first_token, None)
    await service.enroll(access, first, first_token, None)
    await service.enroll(access, second, first_token, None)
    already_member = user()
    access.rebac.members[already_member.uid] = {"demo"}
    await service.enroll(access, already_member, first_token, None)
    # A member added by hand who enrolls through the Free link gets its source too.
    assert events == [
        (
            "platform.access.free.enrolled",
            {"actor_uid": person.uid, "team_id": "demo", "link_id": str(first_id)},
        )
        for person in (first, second, already_member)
    ]
    first_page = await service.list_link_joiners(access, "demo", first_id, 0, 1)
    assert first_page.total == 3 and len(first_page.items) == 1
    assert (await service.list_link_joiners(access, "demo", first_id, 1, 1)).items[
        0
    ].user_id != first_page.items[0].user_id
    assert (
        await service.list_link_joiners(access, "demo", second_id, 0, 25)
    ).total == 0
    assert (await service.list_links(access, "demo", 0, 25)).items[1].opening_count == 1

    access.rebac.members[first.uid].remove("demo")
    await service.enroll(access, first, second_token, None)
    assert events[-1] == (
        "platform.access.free.enrolled",
        {"actor_uid": first.uid, "team_id": "demo", "link_id": str(second_id)},
    )
    assert (await service.list_link_joiners(access, "demo", second_id, 0, 25)).items[
        0
    ].username == "first"
    async with access.store.mutation() as session:
        row = await session.get(UserRow, UUID(first.uid))
        row.last_name = "Updated"
    assert any(
        item.last_name == "Updated"
        for item in (
            await service.list_link_joiners(access, "demo", first_id, 0, 25)
        ).items
    )

    await service.revoke_link(access, "demo", first_id)
    await service.set_team(access, actor, "demo", False, False)
    assert (await service.list_link_joiners(access, "demo", first_id, 0, 25)).total == 3
    assert await service.delete_inactive_links(access, "demo") == 1
    with pytest.raises(HTTPException) as removed:
        await service.list_link_joiners(access, "demo", first_id, 0, 25)
    assert removed.value.status_code == 404
    assert (
        await service.list_link_joiners(access, "demo", second_id, 0, 25)
    ).total == 1
    await service.mark_user_join_history_deleted(access.store, first.uid)
    deleted_joiner = (
        await service.list_link_joiners(access, "demo", second_id, 0, 25)
    ).items[0]
    assert deleted_joiner.deleted
    assert (
        deleted_joiner.username,
        deleted_joiner.first_name,
        deleted_joiner.last_name,
    ) == (
        "first",
        "First",
        "Updated",
    )
    async with access.store.mutation() as session:
        user_row = await session.get(UserRow, UUID(first.uid))
        assert user_row is not None
        await session.delete(user_row)
    assert (await service.list_link_joiners(access, "demo", second_id, 0, 25)).items[
        0
    ] == deleted_joiner
    await service.mark_user_join_history_deleted(
        access.store, second.uid, table_may_be_missing=True
    )
    async with access.store.engine.begin() as connection:
        await connection.run_sync(
            cast(Table, PlatformAccessLinkJoinerRow.__table__).drop
        )
    await service.mark_user_join_history_deleted(
        access.store, first.uid, table_may_be_missing=True
    )


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
async def test_link_admin_history_and_tokens_are_guarded(access, monkeypatch):
    actor = user("accepted")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        api, "emit_audit_log", lambda name, **fields: events.append((name, fields))
    )
    await access.observe(actor)
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo", actor)
    link_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        access.rebac.admin = False
        for method, path in (
            ("GET", "/admin/platform/access/teams/demo/enrollment-links"),
            (
                "GET",
                f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/joiners",
            ),
            (
                "POST",
                f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/reveal",
            ),
            ("DELETE", f"/admin/platform/access/teams/demo/enrollment-links/{link_id}"),
            ("DELETE", "/admin/platform/access/teams/demo/enrollment-links/inactive"),
        ):
            assert (await client.request(method, path)).status_code == 403
        access.rebac.admin = True
        created = await client.post(
            "/admin/platform/access/teams/demo/enrollment-link", json={}
        )
        assert created.status_code == 200
        created_id = next(
            item.id
            for item in (await service.list_links(access, "demo", 0, 25)).items
            if item.id != link_id
        )
        assert (
            "platform.access.link.created",
            {"actor_uid": actor.uid, "team_id": "demo", "link_id": str(created_id)},
        ) in events
        assert created.json()["token"] not in str(events)
        history = await client.get("/admin/platform/access/teams/demo/enrollment-links")
        assert token not in history.text
        await service.enroll(
            access, user().model_copy(update={"username": "link-guest"}), token, None
        )
        joiners = await client.get(
            f"/admin/platform/access/teams/demo/enrollment-links/{link_id}/joiners"
        )
        assert joiners.status_code == 200
        assert joiners.json()["items"][0]["username"] == "link-guest"
        assert token not in joiners.text
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
    await asyncio.gather(
        *(service.record_opening(pg_access, token, user()) for _ in range(4))
    )
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
    assert not await access.admitted(blocked)
    await free_joiner(access, blocked.uid)
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


@pytest.mark.asyncio
async def test_large_bulk_grants_and_late_batch_unknown_roll_back(access):
    from sqlalchemy import func, select

    actor = user("accepted")
    ids = [UUID(int=index + 10000) for index in range(1001)]
    async with access.store.mutation() as session:
        session.add_all(
            [
                UserRow(
                    id=uid,
                    username=f"person{index}",
                    first_name="Demo",
                    last_name=f"Person{index}",
                )
                for index, uid in enumerate(ids)
            ]
        )
        await session.flush()
        await access.store.add_exception(ids[0], actor.uid, "t0", session)
    with pytest.raises(HTTPException, match="user_not_found"):
        await service.grant_users(access, actor, [*ids, UUID(int=2**128 - 1)])
    async with access.store.read() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(PlatformAccessUserRow)
            )
            == 1
        )
    await service.grant_users(access, actor, [*ids, *ids])
    async with access.store.read() as session:
        assert await session.scalar(
            select(func.count()).select_from(PlatformAccessUserRow)
        ) == len(ids)
    assert (await access.store.exception(ids[0])).source == "t0"
    page = await service.users_page(access, 0, 25, "Person1000")
    assert page.total == 1
    assert (
        page.items[0].first_name == "Demo" and page.items[0].last_name == "Person1000"
    )


@pytest.mark.asyncio
async def test_population_preview_distinguishes_fresh_denial_and_uncertain_evidence(
    access,
):
    actor, blocked, stale, granted = user("accepted"), user(), user(), user()
    for person in (actor, blocked, stale, granted):
        await access.observe(person)
    async with access.store.mutation() as session:
        row = await access.store.user(UUID(stale.uid), session)
        row.admission_expires_at = time.time() - 1
    await service.set_user(access, actor, UUID(granted.uid), True)
    before = await access.state()
    preview = await service.activation_preview(access)
    outcomes = {person.user_id: person.outcome for person in preview.users}
    assert outcomes == {
        actor.uid: "allowed",
        blocked.uid: "blocked",
        stale.uid: "unknown",
        granted.uid: "allowed",
    }
    assert (preview.allowed, preview.blocked, preview.unknown) == (2, 1, 1)
    assert not (await access.state()).filtering_enabled
    assert (await access.state()).revision == before.revision
    await service.save_policy(access, actor, draft(), before.revision)
    with pytest.raises(HTTPException, match="platform_access_policy_conflict"):
        await service.set_filtering(access, actor, True, preview.revision)
    assert not (await access.state()).filtering_enabled


@pytest.mark.asyncio
async def test_population_preview_live_free_membership_and_conflicted_evidence(access):
    actor, member = user("accepted"), user()
    await access.observe(actor)
    await access.observe(member)
    async with access.store.mutation() as session:
        (await access.store.user(UUID(member.uid), session)).admission_conflicted = True
    access.rebac.members[member.uid] = {"demo"}
    await service.set_team(access, actor, "demo", False, True)
    await free_joiner(access, member.uid)
    preview = await service.activation_preview(access)
    assert (
        next(row for row in preview.users if row.user_id == member.uid).outcome
        == "allowed"
    )
    access.rebac.members[member.uid].clear()
    preview = await service.activation_preview(access)
    assert (
        next(row for row in preview.users if row.user_id == member.uid).outcome
        == "unknown"
    )


@pytest.mark.asyncio
async def test_population_preview_suspension_overrides_exception_and_requires_admin(
    access,
):
    from unittest.mock import AsyncMock

    from fred_core.security.models import AccountStatusError

    actor = user("accepted")
    await access.observe(actor)
    await service.set_user(access, actor, UUID(actor.uid), True)
    access.rebac.require_active_account = AsyncMock(side_effect=AccountStatusError())
    assert (await service.activation_preview(access)).blocked == 1
    access.rebac.require_active_account.side_effect = AccountStatusError(
        unavailable=True
    )
    assert (await service.activation_preview(access)).unknown == 1
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    access.rebac.admin = False
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get("/admin/platform/access/activation-preview")
        ).status_code == 403


@pytest.mark.asyncio
async def test_users_listing_restricts_to_individual_exceptions_newest_first(
    access, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    actor = user("other")
    names = ["zoe", "Bob", "alice", None]
    ids = [UUID(int=500 - index) for index in range(len(names))]
    day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    grants = {0: (1, "manual"), 1: (3, "t0"), 3: (1, "manual")}
    async with access.store.mutation() as session:
        session.add_all(
            [UserRow(id=uid, username=name) for uid, name in zip(ids, names)]
        )
        await session.flush()
        session.add_all(
            [
                PlatformAccessUserRow(
                    user_id=ids[index],
                    source=source,
                    granted_by=actor.uid,
                    granted_at=day + timedelta(days=offset),
                )
                for index, (offset, source) in grants.items()
            ]
        )
    access.rebac.members[str(ids[0])] = {"demo"}
    async with access.store.mutation() as session:
        (await access.store.team("demo", session)).platform_access_allowed = True

    # The page query already carries each exception: no read per row.
    async def no_row_read(*args, **kwargs):
        raise AssertionError("exception read per row")

    monkeypatch.setattr(access.store, "exception", no_row_read)

    everyone = await service.users_page(access, 0, 25, "")
    assert [item.username for item in everyone.items] == [
        "alice",
        "Bob",
        "zoe",
        str(ids[3]),
    ]
    assert everyone.total == 4
    # No exception: no individual source, hence no grant date.
    assert everyone.items[0].sources == []

    listed = await service.users_page(access, 0, 25, "", True)
    assert [item.user_id for item in listed.items] == [
        str(ids[1]),
        str(ids[0]),
        str(ids[3]),
    ]
    assert listed.total == 3

    # SQLite hands the stored dates back without their zone.
    def moment(value):
        return value.replace(tzinfo=None) if value else None

    first, later = moment(day + timedelta(days=1)), moment(day + timedelta(days=3))
    assert [
        [(source.kind, moment(source.granted_at)) for source in item.sources]
        for item in listed.items
    ] == [
        [("t0", later)],
        [("manual", first), ("team", None)],
        [("manual", first)],
    ]
    # The same row carries the same sources without the filter.
    assert everyone.items[2].sources == listed.items[1].sources
    second = await service.users_page(access, 2, 2, "", True)
    assert [item.user_id for item in second.items] == [str(ids[3])]
    assert second.total == 3
    searched = await service.users_page(access, 0, 25, "o", True)
    assert [item.username for item in searched.items] == ["Bob", "zoe"]
    assert searched.total == 2

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        default = await client.get("/admin/platform/access/users")
        assert default.status_code == 200 and default.json()["total"] == 3
        filtered = await client.get(
            "/admin/platform/access/users",
            params={"exceptions_only": "true", "query": "o", "limit": 1, "offset": 1},
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 2
        item = filtered.json()["items"][0]
        assert item["username"] == "zoe"
        assert [source["kind"] for source in item["sources"]] == ["manual", "team"]
        assert item["sources"][0]["granted_at"].startswith("2026-01-02T00:00:00")


@pytest.mark.asyncio
async def test_pg_user_search_ignores_accents_and_case(pg_access):
    names = [
        ("lea", "Léa"),
        ("elodie", "ÉLODIE"),
        ("helene", "Helene"),
        ("olga", "Ольга"),
    ]
    async with pg_access.store.mutation() as session:
        session.add_all(
            [
                UserRow(id=UUID(int=index + 1), username=username, first_name=first)
                for index, (username, first) in enumerate(names)
            ]
        )

    async def found(query: str) -> list[str | None]:
        page = await service.users_page(pg_access, 0, 25, query)
        assert page.total == len(page.items)
        return [item.username for item in page.items]

    assert await found("LEA") == await found("léa") == ["lea"]
    assert await found("élodie") == await found("elodie") == ["elodie"]
    assert await found("hélène") == ["helene"]
    assert await found("ольга") == ["olga"]
    assert await found("zzz") == []


def refresh_request(
    preview: PlatformT0Preview, mode: PlatformT0RefreshMode = "preserve_removals"
) -> RefreshPlatformT0:
    assert preview.completed_at is not None
    return RefreshPlatformT0(
        mode=mode,
        expected_revision=preview.revision,
        expected_completed_at=preview.completed_at.replace(tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["manual", "t0"])
@pytest.mark.parametrize("filtering", [False, True])
async def test_refresh_preserves_removals_and_can_explicitly_restore_them(
    access, source, filtering
):
    actor, removed, manual, newcomer = user("accepted"), user(), user(), user()
    for person in (removed, manual):
        await access.observe(person)
    await service.set_user(access, actor, UUID(manual.uid), True)
    first = await service.t0(access, actor)
    if source == "manual":
        removed = manual
    await service.set_user(access, actor, UUID(removed.uid), False)
    async with access.store.read() as session:
        history = await session.get(PlatformAccessRemovalRow, UUID(removed.uid))
        assert history.removed_by == actor.uid
        removed_at = history.removed_at
    await service.set_user(access, actor, UUID(removed.uid), False)
    async with access.store.read() as session:
        assert (
            await session.get(PlatformAccessRemovalRow, UUID(removed.uid))
        ).removed_at == removed_at
    await access.observe(newcomer)
    if filtering:
        await service.set_filtering(access, actor, True)
        assert not await access.admitted(newcomer)
    preview = await service.t0(access, refresh_mode="preserve_removals")
    assert preview.candidates == 1 and preview.removed_skipped == 1
    result, count = await service.import_t0(
        access, actor, refresh=refresh_request(preview)
    )
    assert count == result.imported_count == 1
    assert await access.store.exception(UUID(removed.uid)) is None
    assert (await access.store.exception(UUID(newcomer.uid))).source == "t0"
    assert (await access.state()).filtering_enabled is filtering
    if filtering:
        assert await access.admitted(newcomer)
        assert not await access.admitted(removed)
    assert result.completed_at is not None and first.completed_at is not None
    assert result.completed_at > first.completed_at.replace(tzinfo=timezone.utc)
    preview = await service.t0(access, refresh_mode="include_removed")
    result, count = await service.import_t0(
        access, actor, refresh=refresh_request(preview, "include_removed")
    )
    assert count == 1
    assert (await access.store.exception(UUID(removed.uid))).source == "t0"
    assert (await access.state()).filtering_enabled is filtering
    if filtering:
        assert await access.admitted(removed)
        assert not await access.admitted(user())
    # A replay cannot undo a removal performed after the confirmed refresh.
    await service.set_user(access, actor, UUID(removed.uid), False)
    with pytest.raises(HTTPException) as error:
        await service.import_t0(
            access, actor, refresh=refresh_request(preview, "include_removed")
        )
    assert error.value.status_code == 409
    assert await access.store.exception(UUID(removed.uid)) is None


@pytest.mark.asyncio
async def test_refresh_requires_full_reset_for_legacy_history(access):
    actor, person = user("accepted"), user()
    await access.observe(person)
    await service.t0(access, actor)
    await service.set_user(access, actor, UUID(person.uid), False)
    async with access.store.mutation() as session:
        (await access.state(session)).t0_removal_history_complete = False
    status = await service.t0(access)
    assert not status.removal_history_complete
    with pytest.raises(HTTPException) as error:
        await service.import_t0(access, actor, refresh=refresh_request(status))
    assert error.value.detail == "platform_access_t0_full_refresh_required"
    assert not (await service.t0(access)).removal_history_complete
    preview = await service.t0(access, refresh_mode="include_removed")
    result, count = await service.import_t0(
        access, actor, refresh=refresh_request(preview, "include_removed")
    )
    assert count == 1 and result.removal_history_complete
    assert (await service.t0(access, refresh_mode="preserve_removals")).candidates == 0


@pytest.mark.asyncio
async def test_refresh_retains_grant_provenance_and_advances_empty_completion(access):
    actor, person = user("accepted"), user()
    await access.observe(person)
    await service.set_user(access, actor, UUID(person.uid), True)
    grant = await access.store.exception(UUID(person.uid))
    await service.t0(access, actor)
    preview = await service.t0(access, refresh_mode="include_removed")
    result, count = await service.import_t0(
        access, actor, refresh=refresh_request(preview, "include_removed")
    )
    retained = await access.store.exception(UUID(person.uid))
    assert (retained.source, retained.granted_by, retained.granted_at) == (
        grant.source,
        grant.granted_by,
        grant.granted_at,
    )
    assert result.completed_at is not None and preview.completed_at is not None
    assert count == 0 and result.completed_at > preview.completed_at.replace(
        tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_refresh_rejects_changed_policy(access):
    actor = user("accepted")
    await service.t0(access, actor)
    preview = await service.t0(access, refresh_mode="include_removed")
    later = user()
    await access.observe(later)
    await service.save_policy(access, actor, draft("different"), preview.revision)
    with pytest.raises(HTTPException) as error:
        await service.import_t0(
            access, actor, refresh=refresh_request(preview, "include_removed")
        )
    assert error.value.status_code == 409
    assert await access.store.exception(UUID(later.uid)) is None
    assert (await service.t0(access)).completed_at == preview.completed_at


@pytest.mark.asyncio
async def test_keycloak_refresh_imports_new_directory_identity(access):
    actor = user("accepted")
    directory = keycloak_directory(FakeDirectoryAdmin([]))
    await service.import_t0(access, actor, directory)
    later = user()
    directory = keycloak_directory(
        FakeDirectoryAdmin([{"id": later.uid, "username": "new-in-directory"}])
    )
    preview = await service.t0(
        access, directory=directory, refresh_mode="preserve_removals"
    )
    assert preview.candidates == 1
    result, count = await service.import_t0(
        access, actor, directory, refresh=refresh_request(preview)
    )
    assert count == 1 and result.imported_count == 1
    assert (await access.store.exception(UUID(later.uid))).source == "t0"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_pg_refresh_commits_only_once(pg_access):
    import asyncio

    actor = user("accepted")
    await service.t0(pg_access, actor)
    later = user()
    await pg_access.observe(later)
    preview = await service.t0(pg_access, refresh_mode="include_removed")
    request = refresh_request(preview, "include_removed")
    results = await asyncio.gather(
        service.import_t0(pg_access, actor, refresh=request),
        service.import_t0(pg_access, actor, refresh=request),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, HTTPException) and result.status_code == 409
            for result in results
        )
        == 1
    )
    assert (await pg_access.store.exception(UUID(later.uid))).source == "t0"


@pytest.mark.asyncio
async def test_failed_revocation_rolls_back_removal_record(access, monkeypatch):
    actor, person = user("accepted"), user()
    await access.observe(person)
    await service.set_user(access, actor, UUID(person.uid), True)

    async def reject(*args):
        raise HTTPException(409, "platform_access_actor_lockout")

    monkeypatch.setattr(service, "preserve_actor", reject)
    with pytest.raises(HTTPException):
        await service.set_user(access, actor, UUID(person.uid), False)
    assert await access.store.exception(UUID(person.uid)) is not None
    async with access.store.read() as session:
        assert await session.get(PlatformAccessRemovalRow, UUID(person.uid)) is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pg_t0_removal_history_migration(pg_access):
    import runpy
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    migration = runpy.run_path(
        str(
            Path(__file__).parents[1]
            / "alembic/versions/d4e8b2a6f091_add_t0_removal_history.py"
        )
    )
    async with pg_access.store.engine.begin() as connection:
        await connection.execute(text("DROP TABLE platform_access_removals"))
        await connection.execute(
            text(
                "ALTER TABLE platform_access_settings DROP COLUMN t0_removal_history_complete"
            )
        )
        await connection.execute(
            text(
                "UPDATE platform_access_settings SET t0_completed_at = now() WHERE id = 1"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO platform_access_settings (id, revision, filtering_enabled) VALUES (2, 0, false)"
            )
        )

        def upgrade(sync_connection):
            with Operations.context(MigrationContext.configure(sync_connection)):
                migration["upgrade"]()

        await connection.run_sync(upgrade)
        flags = (
            await connection.execute(
                text(
                    "SELECT id, t0_removal_history_complete FROM platform_access_settings ORDER BY id"
                )
            )
        ).all()
        assert flags == [(1, False), (2, True)]
        assert (
            await connection.execute(
                text("SELECT count(*) FROM platform_access_removals")
            )
        ).scalar_one() == 0
        await connection.execute(
            text(
                "INSERT INTO platform_access_settings (id, revision, filtering_enabled) VALUES (3, 0, false)"
            )
        )
        assert (
            await connection.execute(
                text(
                    "SELECT t0_removal_history_complete FROM platform_access_settings WHERE id = 3"
                )
            )
        ).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["filtering", "policy"])
async def test_refresh_rechecks_state_after_directory_preparation(
    access, monkeypatch, change
):
    import asyncio
    import threading

    actor, person = user("accepted"), user()
    await access.observe(person)
    await service.t0(access, actor)
    newcomer = user()
    await access.observe(newcomer)
    preview = await service.t0(access, refresh_mode="include_removed")
    entered, release = threading.Event(), threading.Event()
    original = access.observed_match

    def pause(row, policy):
        entered.set()
        assert release.wait(5)
        return original(row, policy)

    monkeypatch.setattr(access, "observed_match", pause)
    task = asyncio.create_task(
        service.import_t0(
            access, actor, refresh=refresh_request(preview, "include_removed")
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if change == "filtering":
            await service.set_filtering(access, actor, True)
        else:
            await service.save_policy(
                access, actor, draft("different"), preview.revision
            )
    finally:
        release.set()
    if change == "filtering":
        result, count = await task
        assert count == 1 and result.completed_at != preview.completed_at
        assert (await access.state()).filtering_enabled
        assert await access.admitted(newcomer)
        assert not await access.admitted(user())
    else:
        with pytest.raises(HTTPException) as error:
            await task
        assert error.value.status_code == 409
        assert (await service.t0(access)).completed_at == preview.completed_at
        assert await access.store.exception(UUID(newcomer.uid)) is None


@pytest.mark.asyncio
async def test_refresh_audit_reports_actual_additions_and_mode_once(
    access, monkeypatch
):
    actor = user("accepted")
    await service.t0(access, actor)
    later = user()
    await access.observe(later)
    preview = await service.t0(access, refresh_mode="preserve_removals")
    request = refresh_request(preview)
    events = []
    monkeypatch.setattr(
        api, "emit_audit_log", lambda name, **fields: events.append((name, fields))
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_user_service_dependencies] = local_user_deps
    app.dependency_overrides[api.get_current_user] = lambda: actor
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/admin/platform/access/t0-import", json=request.model_dump(mode="json")
        )
        replay = await client.post(
            "/admin/platform/access/t0-import", json=request.model_dump(mode="json")
        )
    assert response.status_code == 200 and replay.status_code == 409
    assert response.json()["imported_count"] == 1
    assert len(events) == 1
    assert events[0][1]["mode"] == "preserve_removals"
    assert events[0][1]["imported_count"] == 1


@pytest.mark.asyncio
async def test_first_import_still_requires_inactive_filtering(access):
    actor, person = user("accepted"), user()
    await access.observe(person)
    await service.set_filtering(access, actor, True)
    with pytest.raises(HTTPException) as error:
        await service.import_t0(access, actor)
    assert error.value.detail == "t0_requires_inactive_filtering"
    assert (await access.state()).filtering_enabled
    assert (await service.t0(access)).completed_at is None
    assert await access.store.exception(UUID(person.uid)) is None
