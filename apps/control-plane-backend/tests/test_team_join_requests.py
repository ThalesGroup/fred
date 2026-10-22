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

"""Team join requests: asking, cancelling, deciding, the 24-hour wait after a
refusal, "Accept anyway", the automatic refusal when a team leaves
`on_request`, expiry, the notifications of both sides and the routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from control_plane_backend.models.team_join_request_models import TeamJoinRequestRow
from control_plane_backend.notifications.service import NotificationService
from control_plane_backend.notifications.store import NotificationStore
from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.temporal.activities import (
    delete_expired_notifications,
)
from control_plane_backend.scheduler.temporal.structures import (
    DeleteExpiredNotificationsInput,
)
from control_plane_backend.teams import api as teams_api
from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)
from control_plane_backend.teams.join_request_store import TeamJoinRequestStore
from control_plane_backend.teams.join_requests import (
    accept_join_request,
    cancel_my_join_request,
    create_join_request,
    list_my_join_requests,
    list_team_join_requests,
    refuse_join_request,
)
from control_plane_backend.teams.schemas import (
    TeamJoinRequestError,
    TeamNotFoundError,
    UpdateTeamRequest,
)
from control_plane_backend.teams.service import delete_team, update_team
from fastapi import FastAPI
from fred_core import (
    JoiningMode,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    TeamVisibility,
    get_current_user,
)
from fred_core.common import TeamId
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.logs.audit_log import AUDIT_LOGGER_NAME
from fred_core.security.models import AuthorizationError
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.asyncio

ATLAS = TeamId("atlas")
_ADMIN_PERMISSIONS = set(TeamPermission)
_EDITOR_PERMISSIONS = {TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_AGENTS}


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], first_name=uid.title())


class _Rebac:
    """Team roles in memory; `team_admin` holds every team permission."""

    def __init__(self) -> None:
        self.roles: dict[str, dict[str, set[RelationType]]] = {
            ATLAS: {
                "bob": {RelationType.TEAM_ADMIN},
                "carol": {RelationType.TEAM_ADMIN},
                "dan": {RelationType.TEAM_EDITOR},
                "erin": {RelationType.PENDING_TEAM_ADMIN},
            }
        }
        self.added: list[Relation] = []

    def _permissions(self, uid: str, team_id: str) -> set[TeamPermission]:
        held = self.roles.get(team_id, {}).get(uid, set())
        if RelationType.TEAM_ADMIN in held:
            return _ADMIN_PERMISSIONS
        if RelationType.TEAM_EDITOR in held:
            return _EDITOR_PERMISSIONS
        return set()

    async def list_direct_relations(self, resource, subject=None, **_):
        return [
            Relation(
                subject=RebacReference(Resource.USER, uid),
                relation=r,
                resource=resource,
            )
            for uid, held in self.roles.get(resource.id, {}).items()
            if subject is None or subject.id == uid
            for r in held
        ]

    async def lookup_subjects(self, resource, relation, _subject_type, **_):
        return [
            RebacReference(Resource.USER, uid)
            for uid, held in self.roles.get(resource.id, {}).items()
            if relation in held
        ]

    async def add_relation(self, relation: Relation, **_) -> None:
        self.added.append(relation)
        team = self.roles.setdefault(relation.resource.id, {})
        team.setdefault(relation.subject.id, set()).add(relation.relation)

    async def check_user_team_permissions_or_raise(self, user, team_id, permissions):
        for permission in permissions:
            if permission not in self._permissions(user.uid, team_id):
                raise AuthorizationError(user.uid, permission.value, Resource.TEAM)

    async def has_permission(self, subject, permission, resource, **_) -> bool:
        return permission in self._permissions(subject.id, resource.id)

    async def has_permissions(self, subject, permissions, resource, **_):
        return [await self.has_permission(subject, p, resource) for p in permissions]

    async def revoke_team_public_relations(self, *_a, **_k):
        return None


class _Teams:
    def __init__(self) -> None:
        self.teams: dict[str, TeamMetadata] = {
            ATLAS: TeamMetadata(
                id=ATLAS,
                name="Atlas",
                joining_mode=JoiningMode.ON_REQUEST,
                visibility=TeamVisibility.PUBLIC,
            )
        }
        self.deleted: list[str] = []

    async def get_by_team_id(self, team_id, session=None):
        return self.teams.get(str(team_id))

    async def upsert(self, team_id, patch, session=None):
        current = self.teams[str(team_id)]
        self.teams[str(team_id)] = current.model_copy(
            update=patch.model_dump(exclude_unset=True)
        )
        return self.teams[str(team_id)]

    async def delete(self, team_id) -> None:
        self.deleted.append(str(team_id))

    @asynccontextmanager
    async def transaction(self):
        yield None


class _World:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.rebac = _Rebac()
        self.teams = _Teams()
        self.requests = TeamJoinRequestStore(engine)
        self.notifications = NotificationService(
            NotificationStore(engine), get_rebac=lambda: cast(Any, self.rebac)
        )
        config = MagicMock()
        config.app.team_admin_charter_version = None
        self.deps = TeamServiceDependencies(
            configuration=config,
            rebac=cast(Any, self.rebac),
            scheduler_backend=cast(Any, object()),
            get_team_metadata_store=cast(Any, lambda: self.teams),
            get_default_team_store=cast(Any, object),
            get_team_admin_charter_store=cast(Any, object),
            get_prompt_store=cast(Any, object),
            get_prompt_category_store=cast(Any, object),
            get_content_store=cast(Any, object),
            get_session_store=cast(Any, object),
            get_purge_queue_store=cast(Any, object),
            get_policy_catalog=cast(Any, object),
            get_users_by_ids=AsyncMock(return_value={}),
            attach_avatar_urls=AsyncMock(side_effect=lambda summaries: summaries),
            search_users=AsyncMock(return_value=[]),
            run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
            get_notification_service=lambda: self.notifications,
            get_team_join_request_store=lambda: self.requests,
        )

    async def ask(self, uid: str = "alice", message: str | None = None):
        return await create_join_request(_user(uid), ATLAS, message, self.deps)

    async def inbox(self, uid: str):
        page = await self.notifications.list_page(_user(uid), limit=50, before=None)
        return page.items

    async def age(self, request_id: str, **shift: timedelta) -> None:
        """Move a request's timestamps into the past."""
        row = TeamJoinRequestRow
        stored = await self.requests.get(ATLAS, request_id)
        assert stored is not None
        values = {
            column: getattr(stored, column) - delta for column, delta in shift.items()
        }
        async with self.engine.begin() as conn:
            await conn.execute(update(row).where(row.id == request_id).values(values))


@pytest_asyncio.fixture
async def world(control_plane_sql_engine: AsyncEngine) -> _World:
    return _World(control_plane_sql_engine)


# --- asking -----------------------------------------------------------------------


async def test_a_request_notifies_only_the_admins_who_can_decide(
    world: _World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
        request, created = await world.ask(message="I run the Lyon pilot")

    assert created and request.status == "pending"
    [stored] = await world.requests.list_for_team(ATLAS)
    assert stored.expires_at - stored.created_at == timedelta(days=30)
    for admin in ("bob", "carol"):
        [tile] = await world.inbox(admin)
        assert tile.type == "team.join_requested" and tile.team_id == ATLAS
        assert tile.payload.model_dump()["requester_name"] == "Alice"
        assert tile.payload.model_dump()["message"] == "I run the Lyon pilot"
    # An editor and an admin who has not accepted the charter cannot decide.
    assert await world.inbox("dan") == [] and await world.inbox("erin") == []

    [event] = [
        r
        for r in caplog.records
        if r.__dict__.get("audit_event") == "team.join_request.created"
    ]
    assert event.__dict__["request_id"] == request.id
    assert "Lyon" not in str(event.__dict__)


async def test_asking_twice_returns_the_pending_request_and_emits_nothing(
    world: _World,
) -> None:
    first, _ = await world.ask()
    [tile] = await world.inbox("bob")
    await world.notifications.mark_seen(_user("bob"), tile.id)

    second, created = await world.ask()

    assert not created and second.id == first.id
    assert (await world.notifications.summary(_user("bob"))).unseen_count == 0


@pytest.mark.parametrize(
    ("mode", "visibility", "uid", "expected"),
    [
        (
            JoiningMode.INVITE_ONLY,
            TeamVisibility.PUBLIC,
            "alice",
            "team_not_on_request",
        ),
        (JoiningMode.OPEN, TeamVisibility.PUBLIC, "alice", "team_not_on_request"),
        (JoiningMode.ON_REQUEST, TeamVisibility.PUBLIC, "dan", "already_team_member"),
        (JoiningMode.ON_REQUEST, TeamVisibility.PRIVATE, "alice", None),
    ],
)
async def test_asking_is_refused_outside_a_public_on_request_team(
    world: _World,
    mode: JoiningMode,
    visibility: TeamVisibility,
    uid: str,
    expected: str | None,
) -> None:
    world.teams.teams[ATLAS] = world.teams.teams[ATLAS].model_copy(
        update={"joining_mode": mode, "visibility": visibility}
    )

    if expected is None:
        # A private team is invisible to a non-member.
        with pytest.raises(TeamNotFoundError):
            await world.ask(uid)
    else:
        with pytest.raises(TeamJoinRequestError) as error:
            await world.ask(uid)
        assert error.value.code == expected
    assert await world.requests.list_for_team(ATLAS) == []
    assert await world.inbox("bob") == []


# --- deciding ---------------------------------------------------------------------


async def test_accept_grants_team_member_only_and_tells_everyone(
    world: _World,
) -> None:
    request, _ = await world.ask()

    await accept_join_request(_user("bob"), ATLAS, request.id, world.deps)

    [grant] = world.rebac.added
    assert grant.subject.id == "alice" and grant.resource.id == ATLAS
    assert grant.relation == RelationType.TEAM_MEMBER
    assert await world.requests.list_for_team(ATLAS) == []
    assert await world.inbox("bob") == []
    [handled] = await world.inbox("carol")
    assert handled.handled_by_name == "Bob" and handled.handled_outcome == "accepted"
    [answer] = await world.inbox("alice")
    assert answer.type == "team.join_request_answered" and answer.team_id is None
    assert answer.payload.model_dump()["outcome"] == "accepted"
    assert "Bob" not in answer.model_dump_json()

    # Carol decides second: the request is gone and Alice stays a member.
    with pytest.raises(TeamJoinRequestError) as error:
        await refuse_join_request(_user("carol"), ATLAS, request.id, world.deps)
    assert error.value.code == "join_request_not_found"


async def test_accepting_someone_who_joined_meanwhile_is_harmless(
    world: _World,
) -> None:
    request, _ = await world.ask()
    world.rebac.roles[ATLAS]["alice"] = {RelationType.TEAM_MEMBER}

    await accept_join_request(_user("bob"), ATLAS, request.id, world.deps)

    assert world.rebac.roles[ATLAS]["alice"] == {RelationType.TEAM_MEMBER}
    assert await world.requests.list_for_team(ATLAS) == []


async def test_a_demoted_admin_loses_the_request_notification(world: _World) -> None:
    await world.ask()
    world.rebac.roles[ATLAS]["carol"] = {RelationType.TEAM_MEMBER}

    await world.notifications.forget_lost_access("carol", ATLAS)

    assert await world.inbox("carol") == []
    assert len(await world.inbox("bob")) == 1


async def test_an_editor_can_neither_list_nor_decide(world: _World) -> None:
    request, _ = await world.ask()
    dan = _user("dan")

    for call in (
        list_team_join_requests(dan, ATLAS, world.deps),
        accept_join_request(dan, ATLAS, request.id, world.deps),
        refuse_join_request(dan, ATLAS, request.id, world.deps),
    ):
        with pytest.raises(AuthorizationError):
            await call

    assert world.rebac.added == []
    [still] = await world.requests.list_for_team(ATLAS)
    assert still.status == "pending"


async def test_refusal_waits_24_hours_then_a_new_request_replaces_it(
    world: _World, caplog: pytest.LogCaptureFixture
) -> None:
    request, _ = await world.ask(message="please")

    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
        await refuse_join_request(_user("bob"), ATLAS, request.id, world.deps)
    # Refusing twice changes nothing.
    await refuse_join_request(_user("carol"), ATLAS, request.id, world.deps)

    [event] = [
        r
        for r in caplog.records
        if r.__dict__.get("audit_event") == "team.join_request.refused"
    ]
    assert event.__dict__["actor_uid"] == "bob"
    assert event.__dict__["requester_uid"] == "alice"
    assert "please" not in str(event.__dict__)

    [refused] = await world.requests.list_for_team(ATLAS)
    assert refused.status == "refused"
    assert refused.decided_at and refused.expires_at - refused.decided_at == (
        timedelta(days=7)
    )
    [handled] = await world.inbox("carol")
    assert handled.handled_outcome == "refused"
    [answer] = await world.inbox("alice")
    assert answer.payload.model_dump()["outcome"] == "refused"
    [mine] = await list_my_join_requests(_user("alice"), world.deps)
    assert mine.status == "refused"
    assert mine.can_ask_again_at == refused.decided_at + timedelta(hours=24)

    with pytest.raises(TeamJoinRequestError) as error:
        await world.ask()
    assert error.value.code == "join_request_refused"

    await world.age(request.id, decided_at=timedelta(hours=25))
    again, created = await world.ask()

    assert created and again.id != request.id and again.status == "pending"
    [only] = await world.requests.list_for_team(ATLAS)
    assert only.id == again.id
    assert [n.payload.model_dump()["request_id"] for n in await world.inbox("bob")] == [
        again.id
    ]


async def test_accept_anyway_replaces_the_refusal_within_7_days(world: _World) -> None:
    request, _ = await world.ask()
    await refuse_join_request(_user("bob"), ATLAS, request.id, world.deps)
    await world.age(request.id, decided_at=timedelta(days=3))

    await accept_join_request(_user("carol"), ATLAS, request.id, world.deps)

    assert [r.subject.id for r in world.rebac.added] == ["alice"]
    assert await world.requests.list_for_team(ATLAS) == []
    [answer] = await world.inbox("alice")
    assert answer.payload.model_dump()["outcome"] == "accepted"


async def test_accept_anyway_shows_the_final_outcome_on_every_admin_tile(
    world: _World,
) -> None:
    request, _ = await world.ask()
    await refuse_join_request(_user("bob"), ATLAS, request.id, world.deps)
    [refused] = await world.inbox("carol")
    assert refused.handled_outcome == "refused"

    await accept_join_request(_user("bob"), ATLAS, request.id, world.deps)

    [handled] = await world.inbox("carol")
    assert handled.handled_by_name == "Bob" and handled.handled_outcome == "accepted"
    assert await world.inbox("bob") == []


async def test_a_refusal_older_than_7_days_is_gone(world: _World) -> None:
    request, _ = await world.ask()
    await refuse_join_request(_user("bob"), ATLAS, request.id, world.deps)
    await world.age(request.id, expires_at=timedelta(days=7, seconds=1))

    assert await list_team_join_requests(_user("bob"), ATLAS, world.deps) == []
    assert await list_my_join_requests(_user("alice"), world.deps) == []
    with pytest.raises(TeamJoinRequestError):
        await accept_join_request(_user("bob"), ATLAS, request.id, world.deps)
    # Expired: Alice may ask again at once.
    assert (await world.ask())[1]


async def test_an_emission_failure_does_not_fail_the_decision(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _ = await world.ask()

    async def _down(*_a, **_k):
        raise RuntimeError("database down")

    monkeypatch.setattr(world.notifications.store, "upsert", _down)
    monkeypatch.setattr(world.notifications.store, "resolve", _down)

    await accept_join_request(_user("bob"), ATLAS, request.id, world.deps)

    assert [r.subject.id for r in world.rebac.added] == ["alice"]


# --- cancelling, mode changes, cleanup -----------------------------------------------


async def test_cancel_deletes_the_request_and_the_admins_notifications(
    world: _World,
) -> None:
    request, _ = await world.ask()

    await cancel_my_join_request(_user("alice"), ATLAS, world.deps)

    assert await list_my_join_requests(_user("alice"), world.deps) == []
    assert await world.inbox("bob") == [] and await world.inbox("carol") == []
    for call in (
        cancel_my_join_request(_user("alice"), ATLAS, world.deps),
        accept_join_request(_user("bob"), ATLAS, request.id, world.deps),
    ):
        with pytest.raises(TeamJoinRequestError) as error:
            await call
        assert error.value.code == "join_request_not_found"


@pytest.mark.parametrize(
    "patch",
    [{"joining_mode": "invite_only"}, {"visibility": "private"}],
)
async def test_leaving_on_request_refuses_every_pending_request(
    world: _World, monkeypatch: pytest.MonkeyPatch, patch: dict[str, str]
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.teams.service._build_team_with_permissions",
        AsyncMock(return_value=None),
    )
    alice, _ = await world.ask("alice")
    frank, _ = await world.ask("frank")

    await update_team(
        _user("bob"), ATLAS, UpdateTeamRequest.model_validate(patch), world.deps
    )

    assert world.teams.teams[ATLAS].joining_mode == JoiningMode.INVITE_ONLY
    listed = await list_team_join_requests(_user("bob"), ATLAS, world.deps)
    assert {(r.id, r.status) for r in listed} == {
        (alice.id, "refused"),
        (frank.id, "refused"),
    }
    for uid in ("alice", "frank"):
        [answer] = await world.inbox(uid)
        assert answer.payload.model_dump()["outcome"] == "refused"
    assert await world.inbox("bob") == []
    assert {n.handled_by_name for n in await world.inbox("carol")} == {"Bob"}


async def test_a_public_team_opts_in_without_refusing_anything(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.teams.service._build_team_with_permissions",
        AsyncMock(return_value=None),
    )
    world.teams.teams[ATLAS] = world.teams.teams[ATLAS].model_copy(
        update={"joining_mode": JoiningMode.INVITE_ONLY}
    )

    await update_team(
        _user("bob"),
        ATLAS,
        UpdateTeamRequest.model_validate({"joining_mode": "on_request"}),
        world.deps,
    )

    assert world.teams.teams[ATLAS].joining_mode == JoiningMode.ON_REQUEST
    assert (await world.ask())[1]


async def test_deleting_the_team_or_the_requester_removes_requests(
    world: _World,
) -> None:
    request, _ = await world.ask("alice")
    await world.ask("frank")

    assert await world.requests.delete_for_requester("alice") == [request.id]
    assert [r.requester_id for r in await world.requests.list_for_team(ATLAS)] == [
        "frank"
    ]

    world.rebac.delete_all_relations_of_reference = AsyncMock()  # type: ignore[attr-defined]
    world.rebac.check_user_permission_or_raise = AsyncMock()  # type: ignore[attr-defined]
    await delete_team(_user("root"), ATLAS, world.deps)

    assert await world.requests.list_for_team(ATLAS) == []


async def test_the_expiry_activity_also_deletes_expired_requests(
    world: _World,
) -> None:
    old, _ = await world.ask("alice")
    await world.ask("frank")
    await world.age(old.id, expires_at=timedelta(days=31))
    deps = LifecycleActionDependencies(
        get_session_store=None,  # type: ignore[arg-type]
        get_purge_queue_store=None,  # type: ignore[arg-type]
        erase_session=None,  # type: ignore[arg-type]
        get_service_bearer=None,  # type: ignore[arg-type]
        get_task_service=None,  # type: ignore[arg-type]
        get_team_wiki_store=None,  # type: ignore[arg-type]
        get_policy_catalog=None,  # type: ignore[arg-type]
        get_team_join_request_store=lambda: world.requests,
    )

    result = await delete_expired_notifications(
        DeleteExpiredNotificationsInput(limit=1000), deps=deps
    )

    assert result.deleted == 1
    async with world.engine.begin() as conn:
        remaining = (
            await conn.execute(TeamJoinRequestRow.__table__.select())
        ).fetchall()
    assert [row.requester_id for row in remaining] == ["frank"]


# --- routes -------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(world: _World) -> AsyncIterator[tuple[AsyncClient, list[str]]]:
    caller = ["alice"]
    app = FastAPI()
    app.include_router(teams_api.router)
    register_exception_handlers(app)
    teams_api.register_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: _user(caller[0])
    app.dependency_overrides[get_team_service_dependencies] = lambda: world.deps
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http, caller


async def test_routes_ask_list_decide_and_cancel(world: _World, client) -> None:
    http, caller = client
    base = f"/teams/{ATLAS}/join-requests"

    first = await http.post(base, json={"message": "  hello  "})
    assert first.status_code == 201
    request_id = first.json()["id"]
    assert (await http.post(base, json={})).status_code == 200
    assert (await http.post(base, json={"message": "x" * 281})).status_code == 422
    [mine] = (await http.get("/teams/join-requests/mine")).json()
    assert mine["status"] == "pending" and mine["team_id"] == ATLAS

    caller[0] = "dan"
    assert (await http.get(base)).status_code == 403
    assert (await http.post(f"{base}/{request_id}/refuse")).status_code == 403

    caller[0] = "bob"
    [listed] = (await http.get(base)).json()
    assert listed["message"] == "hello" and listed["requester_name"] == "Alice"
    assert (await http.post(f"{base}/{request_id}/refuse")).status_code == 204
    assert (await http.post(f"{base}/{request_id}/accept")).status_code == 204
    missing = await http.post(f"{base}/{request_id}/refuse")
    assert missing.status_code == 404
    assert missing.json()["code"] == "join_request_not_found"

    caller[0] = "frank"
    assert (await http.post(base, json={})).status_code == 201
    assert (await http.delete(f"{base}/mine")).status_code == 204
    assert (await http.delete(f"{base}/mine")).status_code == 404

    caller[0] = "dan"
    taken = await http.post(base, json={})
    assert taken.status_code == 409 and taken.json()["code"] == "already_team_member"


async def test_join_request_routes_reject_an_unauthenticated_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from fred_core.security import oidc

    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    app = create_app()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    get_application_container_from_app(app).configuration.security.user.enabled = True
    base = "/control-plane/v1/teams"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        responses = [
            await http.get(f"{base}/join-requests/mine"),
            await http.post(f"{base}/atlas/join-requests", json={}),
            await http.delete(f"{base}/atlas/join-requests/mine"),
            await http.get(f"{base}/atlas/join-requests"),
            await http.post(f"{base}/atlas/join-requests/r1/accept"),
            await http.post(f"{base}/atlas/join-requests/r1/refuse"),
        ]

    assert [response.status_code for response in responses] == [401] * 6
