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
