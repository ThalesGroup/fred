# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import AsyncIterator
import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, event, insert, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from fred_core.teams.space_models import SpaceRow
from fred_core.users.store.base_user_store import OrganizationAssignmentError
from fred_core.users.store.postgres_user_store import PostgresUserStore
from fred_core.users.user_models import UserRow


@pytest_asyncio.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
async def database(tmp_path, request) -> AsyncIterator[AsyncEngine]:
    schema = f"admission_test_{uuid4().hex}"
    options = {}
    url = make_url(f"sqlite+aiosqlite:///{tmp_path / 'admission.db'}")
    if request.param == "postgresql":
        configured = os.environ.get("FRED_SPACE_TEST_POSTGRES_URL")
        if not configured:
            pytest.skip("Set FRED_SPACE_TEST_POSTGRES_URL for isolated-schema checks")
        url = make_url(configured).set(drivername="postgresql+asyncpg")
        options = {"server_settings": {"search_path": schema}}
    engine = create_async_engine(url, connect_args=options)
    # PostgreSQL emits ALTER constraints; keep its DDL state local to this fixture.
    metadata = MetaData()
    UserRow.__table__.to_metadata(metadata)
    SpaceRow.__table__.to_metadata(metadata)
    if request.param == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys = ON")

    try:
        async with engine.begin() as connection:
            if request.param == "postgresql":
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(metadata.create_all)
            for identifier in ("org-a", "org-b"):
                await connection.execute(
                    insert(SpaceRow).values(
                        id=identifier, kind="organization", name=identifier
                    )
                )
            await connection.execute(
                insert(SpaceRow).values(
                    id="team-a",
                    name="Team",
                    kind="team",
                    parent_id="org-a",
                    parent_kind="organization",
                    team_kind="collaborative",
                )
            )
        yield engine
    finally:
        if request.param == "postgresql":
            async with engine.begin() as connection:
                await connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        await engine.dispose()


@pytest_asyncio.fixture
async def identity(database: AsyncEngine) -> tuple[PostgresUserStore, UUID]:
    store = PostgresUserStore(database)
    user_id = uuid4()
    await store.upsert_identity(user_id, "alice", None, None, None)
    return store, user_id


@pytest.mark.asyncio
async def test_identity_updates_do_not_choose_or_replace_an_organization(identity):
    store, user_id = identity
    pending = await store.find_user_by_id(user_id)
    assert pending.organization_id is None
    await store.assign_organization(user_id, "org-a")
    await store.upsert_identity(user_id, "renamed", None, None, None)
    await store.update_gcu_version(user_id, "v1")
    await store.swap_avatar_key(user_id, "avatar")
    await store.increment_current_storage_size(user_id, 10)
    admitted = await store.find_user_by_id(user_id)
    assert admitted.organization_id == "org-a"
    assert admitted.username == "renamed"


@pytest.mark.asyncio
async def test_assignment_is_one_statement_and_same_target_is_repeatable(
    database, identity
):
    store, user_id = identity
    statements = []

    @event.listens_for(database.sync_engine, "before_cursor_execute")
    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    await store.assign_organization(user_id, "org-a")
    await store.assign_organization(user_id, "org-a")
    assert len(statements) == 2
    assert all(statement.startswith("UPDATE users") for statement in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["missing", "team-a"])
async def test_assignment_requires_an_existing_organization(identity, target):
    store, user_id = identity
    with pytest.raises(IntegrityError):
        await store.assign_organization(user_id, target)
    assert (await store.find_user_by_id(user_id)).organization_id is None


@pytest.mark.asyncio
async def test_discriminator_cannot_disguise_a_team_as_an_organization(
    database, identity
):
    _store, user_id = identity
    with pytest.raises(IntegrityError):
        async with database.begin() as connection:
            await connection.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(organization_id="team-a", organization_kind="team")
            )


@pytest.mark.asyncio
async def test_missing_identity_is_not_created_by_admission(identity):
    store, _user_id = identity
    unknown = uuid4()
    with pytest.raises(OrganizationAssignmentError):
        await store.assign_organization(unknown, "org-a")
    assert await store.find_user_by_id(unknown) is None


@pytest.mark.asyncio
async def test_competing_organizations_cannot_replace_the_winning_assignment(identity):
    store, user_id = identity
    outcomes = await asyncio.gather(
        store.assign_organization(user_id, "org-a"),
        store.assign_organization(user_id, "org-b"),
        return_exceptions=True,
    )
    assert outcomes.count(None) == 1
    assert (
        sum(isinstance(outcome, OrganizationAssignmentError) for outcome in outcomes)
        == 1
    )
    winner = "org-a" if outcomes[0] is None else "org-b"
    assert (await store.find_user_by_id(user_id)).organization_id == winner


@pytest.mark.asyncio
async def test_assignment_participates_in_the_callers_transaction(database, identity):
    store, user_id = identity
    with pytest.raises(RuntimeError, match="rollback"):
        async with AsyncSession(database) as session, session.begin():
            await store.assign_organization(user_id, "org-a", session=session)
            raise RuntimeError("rollback")
    assert (await store.find_user_by_id(user_id)).organization_id is None


@pytest_asyncio.fixture
async def spaces(database, identity):
    from fred_core.teams.space_store import SpaceStore

    users, owner = identity
    await users.assign_organization(owner, "org-a")
    other = uuid4()
    await users.upsert_identity(other, "bob", None, None, None)
    await users.assign_organization(other, "org-a")
    store = SpaceStore(database)
    personal = await store.create_personal_team(owner, "org-a")
    other_personal = await store.create_personal_team(other, "org-a")
    async with database.begin() as connection:
        await connection.execute(
            insert(SpaceRow).values(
                id="project-a",
                kind="project",
                name="Project",
                parent_id="team-a",
                parent_kind="team",
                parent_team_kind="collaborative",
            )
        )
        await connection.execute(
            insert(SpaceRow).values(
                id="team-b",
                kind="team",
                name="Team",
                parent_id="org-b",
                parent_kind="organization",
                team_kind="collaborative",
            )
        )
    return store, owner, personal, other_personal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (None, (("organization", "org-a"),)),
        ("org-a", (("organization", "org-a"),)),
        ("team-a", (("team", "team-a"), ("organization", "org-a"))),
        (
            "project-a",
            (("project", "project-a"), ("team", "team-a"), ("organization", "org-a")),
        ),
    ],
)
async def test_space_context_is_one_bounded_query(
    database, spaces, identifier, expected
):
    store, owner, _, _ = spaces
    statements = []

    @event.listens_for(database.sync_engine, "before_cursor_execute")
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    context = await store.resolve_for_user(owner, identifier)
    assert context is not None
    assert context.ancestry == expected
    assert context.organization_id == "org-a"
    assert context.team_id == (None if identifier in (None, "org-a") else "team-a")
    assert len(statements) == 1
    assert statements[0].startswith("SELECT")
    assert "RECURSIVE" not in statements[0]


@pytest.mark.asyncio
async def test_space_resolution_refuses_foreign_unknown_and_unadmitted_users(
    database, spaces
):
    store, owner, _, other_personal = spaces
    pending = uuid4()
    users = PostgresUserStore(database)
    await users.upsert_identity(pending, "pending", None, None, None)
    for user, target in (
        (owner, "org-b"),
        (owner, "team-b"),
        (owner, "missing"),
        (owner, other_personal),
        (pending, "org-a"),
        (uuid4(), "team-a"),
    ):
        assert await store.resolve_for_user(user, target) is None


@pytest.mark.asyncio
async def test_personal_resolution_has_only_its_owner_and_organization(spaces):
    store, owner, personal, _ = spaces
    context = await store.resolve_for_user(owner, personal)
    assert context is not None
    assert context.ancestry == (("team", personal), ("organization", "org-a"))
    assert context.team_id == personal
    assert await store.create_personal_team(owner, "org-a") == personal
    with pytest.raises(ValueError, match="owner's organization"):
        await store.create_personal_team(owner, "org-b")


@pytest.mark.asyncio
async def test_organization_creation_does_not_reinterpret_existing_spaces(spaces):
    store, _, _, _ = spaces
    assert await store.create_organization("org-c", "Third") is True
    assert await store.create_organization("org-c", "Third") is False
    for identifier, name in (("org-c", "Changed"), ("team-a", "Team")):
        with pytest.raises(ValueError, match="conflicts"):
            await store.create_organization(identifier, name)


class _SpaceDecisions:
    def __init__(self, allowed_ids):
        self.allowed_ids = set(allowed_ids)
        self.calls = []

    async def has_permissions(self, subject, checks, **kwargs):
        self.calls.append((subject, checks, kwargs))
        return [reference.id in self.allowed_ids for _, reference in checks]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    ["READ_CORPUS", "USE_AGENTS", "EDIT_CORPUS", "ANALYZE", "ADMINISTER_MEMBERS"],
)
async def test_space_access_batches_only_the_operation_scope(spaces, operation):
    from fred_core.security.rebac.rebac_engine import RebacEngine, SpacePermission
    from fred_core.security.rebac.space_authorization import authorize_space
    from fred_core.security.structure import KeycloakUser

    store, owner, _, _ = spaces
    permission = SpacePermission[operation]
    rebac = _SpaceDecisions({"project-a", "team-a", "org-a"})
    access = await authorize_space(
        KeycloakUser(uid=str(owner), username="alice", roles=[]),
        "project-a",
        permission,
        spaces=store,
        rebac=rebac,
    )
    expected = (
        ("project-a", "team-a", "org-a")
        if operation in ("READ_CORPUS", "USE_AGENTS")
        else ("project-a",)
    )
    assert access.space_ids == expected
    assert access.context.team_id == "team-a"
    assert len(rebac.calls) == 1
    assert [reference.id for _, reference in rebac.calls[0][1]] == list(expected)
    assert rebac.calls[0][2]["consistency_token"] == RebacEngine.HIGHER_CONSISTENCY


@pytest.mark.asyncio
async def test_space_access_excludes_denied_ancestors_and_rechecks_next_request(spaces):
    from fred_core.security.models import AuthorizationError
    from fred_core.security.rebac.rebac_engine import SpacePermission
    from fred_core.security.rebac.space_authorization import authorize_space
    from fred_core.security.structure import KeycloakUser

    store, owner, _, _ = spaces
    user = KeycloakUser(uid=str(owner), username="alice", roles=[])
    rebac = _SpaceDecisions({"project-a", "org-a"})
    access = await authorize_space(
        user, "project-a", SpacePermission.READ_CORPUS, spaces=store, rebac=rebac
    )
    assert access.space_ids == ("project-a", "org-a")
    rebac.allowed_ids.remove("project-a")
    with pytest.raises(AuthorizationError):
        await authorize_space(
            user, "project-a", SpacePermission.READ_CORPUS, spaces=store, rebac=rebac
        )
    assert len(rebac.calls) == 2


@pytest.mark.asyncio
async def test_foreign_space_never_reaches_the_permission_engine(spaces):
    from fred_core.security.models import AuthorizationError
    from fred_core.security.rebac.rebac_engine import SpacePermission
    from fred_core.security.rebac.space_authorization import authorize_space
    from fred_core.security.structure import KeycloakUser

    store, owner, _, _ = spaces
    rebac = _SpaceDecisions({"org-b"})
    for uid, target in ((str(owner), "org-b"), ("malformed", "org-a")):
        with pytest.raises(AuthorizationError):
            await authorize_space(
                KeycloakUser(uid=uid, username="alice", roles=[]),
                target,
                SpacePermission.READ_CORPUS,
                spaces=store,
                rebac=rebac,
            )
    assert rebac.calls == []


@pytest.mark.asyncio
async def test_organization_candidate_filter_is_one_query(database, identity):
    store, admitted = identity
    await store.assign_organization(admitted, "org-a")
    pending, foreign, missing = uuid4(), uuid4(), uuid4()
    await store.upsert_identity(pending, "pending", None, None, None)
    await store.upsert_identity(foreign, "foreign", None, None, None)
    await store.assign_organization(foreign, "org-b")
    statements = []

    @event.listens_for(database.sync_engine, "before_cursor_execute")
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    assert await store.filter_organization_users(
        [admitted, admitted, pending, foreign, missing], "org-a"
    ) == {admitted}
    assert len(statements) == 1
    assert statements[0].startswith("SELECT")


@pytest.mark.asyncio
async def test_unadmitted_user_never_reaches_fga(database, identity):
    from fred_core.security.models import AuthorizationError
    from fred_core.security.rebac.rebac_engine import SpacePermission
    from fred_core.security.rebac.space_authorization import authorize_space
    from fred_core.security.structure import KeycloakUser
    from fred_core.teams.space_store import SpaceStore

    _, pending = identity
    rebac = _SpaceDecisions({"org-a"})
    for target in (None, "org-a", "team-a"):
        with pytest.raises(AuthorizationError):
            await authorize_space(
                KeycloakUser(uid=str(pending), username="pending", roles=[]),
                target,
                SpacePermission.READ_CORPUS,
                spaces=SpaceStore(database),
                rebac=rebac,
            )
    assert rebac.calls == []
