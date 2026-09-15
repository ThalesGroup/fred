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

"""`TeamWikiStore`'s structural writers, executed against a real PostgreSQL.

Why this file exists, and why SQLite cannot replace it: the invariant under
test — every committed wiki tree stays acyclic, within `MAX_PAGE_DEPTH`, and
free of references to a deleted parent — is a cross-row, cross-transaction
guarantee. `test_team_wiki_store.py` proves each structural check fires
correctly for a SINGLE writer; it cannot prove two writers racing each other
stay serialized, because SQLite in these tests is single-connection and
`_structural_lock`'s `pg_advisory_xact_lock` is a documented no-op on it (see
the lock's docstring in `store.py`). Only a real Postgres server, with two
genuinely concurrent transactions on the same database, exercises the
serialization this fix adds.

Each test below launches two structural writers with `asyncio.gather` — real
concurrency, not a sequential simulation — and then reads back the FULL page
tree to assert the committed invariant directly, rather than only checking
that one side raised an exception. An exception on the losing side is
necessary but not sufficient: the bug this fixes was never "no error is
raised", it was "both sides land, and the committed rows are the proof".

Run:

    docker compose -f scripts/docker-compose.postgres.yml up -d
    export FRED_PG_DSN="postgresql+asyncpg://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret
    .venv/bin/pytest tests/test_team_wiki_store_postgres_integration.py -m integration_postgres

Each test gets its own throwaway schema (dropped on teardown) via a
connection-level `search_path`, so this never reads or writes any other
table in the target database, and a unique per-test team id keeps advisory
lock keys (database-wide, not schema-scoped) from colliding across tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.team_wiki_models import MAX_PAGE_DEPTH
from control_plane_backend.team_wiki.store import (
    TeamWikiStore,
    WikiPageDepthExceededError,
    WikiPageHasChildrenError,
    WikiPageInvalidMoveError,
    WikiPageNotFoundError,
    WikiPageRecord,
    WikiProposalNoLongerPendingError,
)
from fred_core.common import TeamId
from sqlalchemy import Update, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
_DEFAULT_DSN = "postgresql+asyncpg://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret


class _Fixture:
    def __init__(self, store: TeamWikiStore, team_id: TeamId) -> None:
        self.store = store
        self.team_id = team_id


@pytest_asyncio.fixture
async def pg() -> AsyncIterator[_Fixture]:
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    schema = f"team_wiki_itest_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await admin.dispose()

    # search_path scopes every unqualified table this engine touches to the
    # throwaway schema — the ORM models declare no schema of their own, so
    # this is what keeps two test runs (or this suite and a real dev stack on
    # the same database) from ever seeing each other's rows.
    engine: AsyncEngine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)

    try:
        yield _Fixture(TeamWikiStore(engine=engine), TeamId(f"team-{schema}"))
    finally:
        await engine.dispose()
        admin = create_async_engine(dsn)
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def _assert_committed_tree_is_sound(
    store: TeamWikiStore, team_id: TeamId
) -> None:
    """The invariant this whole fix exists to hold: acyclic, within the depth
    cap, and no page pointing at a parent that isn't there."""

    pages: dict[str, WikiPageRecord] = {
        p.page_id: p for p in await store.list_pages(team_id)
    }
    for page in pages.values():
        if page.parent_page_id is not None:
            assert page.parent_page_id in pages, (
                f"{page.page_id} points at a parent that no longer exists"
            )
        depth = 0
        cursor = page.parent_page_id
        seen = {page.page_id}
        while cursor is not None:
            assert cursor not in seen, f"cycle reaches back to {page.page_id}"
            seen.add(cursor)
            depth += 1
            assert depth <= MAX_PAGE_DEPTH, (
                f"{page.page_id} sits past the depth cap ({depth} > {MAX_PAGE_DEPTH})"
            )
            parent = pages.get(cursor)
            cursor = parent.parent_page_id if parent else None


@contextlib.asynccontextmanager
async def _pause_before_the_proposal_publish_write(
    reached: asyncio.Event, release: asyncio.Event
) -> AsyncIterator[None]:
    """Forces the interleaving `publish_proposal`'s CAS exists for: a reject
    committing between its SELECT and its own write. Plain `asyncio.gather`
    cannot guarantee that window is hit (see CONTROL-PLANE-PRODUCT-CONTRACT.md
    §49's 2026-09-08 correction) — this pauses `AsyncSession.execute` for the
    one statement matching that write's compiled SQL instead.
    """

    original_execute = AsyncSession.execute

    async def _patched(
        self: AsyncSession, statement: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if (
            isinstance(statement, Update)
            and getattr(statement.table, "name", None) == "team_wiki_revisions"
            and "author_user_id" in str(statement)
        ):
            reached.set()
            await release.wait()
        return await original_execute(self, statement, *args, **kwargs)

    AsyncSession.execute = _patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        AsyncSession.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_a_single_structural_write_still_works_on_real_postgres(
    pg: _Fixture,
) -> None:
    """Smoke test: the `pg_advisory_xact_lock` branch (SQLite never exercises
    it) does not itself break the ordinary, uncontested path."""

    store = pg.store
    created = await store.create_page(
        team_id=pg.team_id, slug="p", title="P", content_md="x", author_user_id="alice"
    )
    moved = await store.update_page_metadata(
        team_id=pg.team_id,
        page_id=created.page.page_id,
        title="P renamed",
        updated_by="alice",
    )
    assert moved.title == "P renamed"
    await store.delete_page(team_id=pg.team_id, page_id=created.page.page_id)
    assert await store.get_page(pg.team_id, created.page.page_id) is None


@pytest.mark.asyncio
async def test_opposing_moves_never_both_commit(pg: _Fixture) -> None:
    """A under B and B under A, launched together. The tree cannot hold both
    edges — exactly one side must lose, never neither and never both."""

    store = pg.store
    a = await store.create_page(
        team_id=pg.team_id, slug="a", title="a", content_md="", author_user_id="x"
    )
    b = await store.create_page(
        team_id=pg.team_id, slug="b", title="b", content_md="", author_user_id="x"
    )

    async def _move(page_id: str, parent_id: str) -> str:
        try:
            await store.update_page_metadata(
                team_id=pg.team_id,
                page_id=page_id,
                parent_page_id=parent_id,
                updated_by="x",
            )
            return "moved"
        except WikiPageInvalidMoveError:
            return "rejected"

    results = await asyncio.gather(
        _move(a.page.page_id, b.page.page_id),
        _move(b.page.page_id, a.page.page_id),
    )

    assert sorted(results) == ["moved", "rejected"]
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_parent_deletion_races_child_creation_without_orphaning(
    pg: _Fixture,
) -> None:
    """A child insert naming this parent, and a delete of that same parent,
    launched together. Never both: a created child under a deleted parent is
    exactly the orphan this fix exists to prevent."""

    store = pg.store
    parent = await store.create_page(
        team_id=pg.team_id,
        slug="parent",
        title="parent",
        content_md="",
        author_user_id="x",
    )

    async def _delete() -> str:
        try:
            await store.delete_page(team_id=pg.team_id, page_id=parent.page.page_id)
            return "deleted"
        except WikiPageHasChildrenError:
            return "has_children"

    async def _create_child() -> str:
        try:
            await store.create_page(
                team_id=pg.team_id,
                slug="child",
                title="child",
                content_md="",
                parent_page_id=parent.page.page_id,
                author_user_id="x",
            )
            return "created"
        except WikiPageNotFoundError:
            return "parent_gone"

    results = await asyncio.gather(_delete(), _create_child())

    assert not ("deleted" in results and "created" in results)
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_parent_deletion_races_proposal_publication_beneath_it(
    pg: _Fixture,
) -> None:
    """The parent named by a pending proposal is deleted at the same moment a
    human approves that proposal. Publishing must land the new page at the
    root rather than under a parent that is gone — never dangling — and it
    must never leave the parent both deleted AND still holding a child."""

    store = pg.store
    parent = await store.create_page(
        team_id=pg.team_id,
        slug="parent2",
        title="parent2",
        content_md="",
        author_user_id="x",
    )
    proposal = await store.create_proposal(
        team_id=pg.team_id,
        page_id=None,
        content_md="drafted by an agent",
        base_revision_id=None,
        proposed_title="Child of parent2",
        proposed_parent_page_id=parent.page.page_id,
        author_user_id="alice",
        agent_instance_id="inst-1",
        session_id="sess-1",
    )

    async def _delete() -> str:
        try:
            await store.delete_page(team_id=pg.team_id, page_id=parent.page.page_id)
            return "deleted"
        except WikiPageHasChildrenError:
            return "has_children"

    async def _publish() -> WikiPageRecord:
        return await store.publish_proposal(
            team_id=pg.team_id,
            revision_id=proposal.revision_id,
            slug="child2",
            approver_user_id="alice",
        )

    delete_result, published = await asyncio.gather(_delete(), _publish())

    if delete_result == "deleted":
        assert published.parent_page_id is None
    else:
        assert delete_result == "has_children"
        assert published.parent_page_id == parent.page.page_id
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_concurrent_structural_writes_never_exceed_the_depth_cap(
    pg: _Fixture,
) -> None:
    """A plain move that would push `p` to the depth cap, and a proposal
    publication that would add a page under `p`, launched together. Each is
    legal on its own against the tree as it stood when the transaction
    started; only one may land without pushing something past
    `MAX_PAGE_DEPTH` — which one depends on serialization order, but never
    both."""

    store = pg.store
    p = await store.create_page(
        team_id=pg.team_id, slug="p3", title="p3", content_md="", author_user_id="x"
    )
    proposal = await store.create_proposal(
        team_id=pg.team_id,
        page_id=None,
        content_md="drafted by an agent",
        base_revision_id=None,
        proposed_title="TooDeep",
        proposed_parent_page_id=p.page.page_id,
        author_user_id="alice",
        agent_instance_id="inst-1",
        session_id="sess-1",
    )
    anchor = await store.create_page(
        team_id=pg.team_id,
        slug="anchor2",
        title="anchor2",
        content_md="",
        author_user_id="x",
    )
    mid1 = await store.create_page(
        team_id=pg.team_id,
        slug="mid1b",
        title="mid1b",
        content_md="",
        parent_page_id=anchor.page.page_id,
        author_user_id="x",
    )
    mid2 = await store.create_page(
        team_id=pg.team_id,
        slug="mid2b",
        title="mid2b",
        content_md="",
        parent_page_id=mid1.page.page_id,
        author_user_id="x",
    )

    async def _move_p_deeper() -> str:
        try:
            await store.update_page_metadata(
                team_id=pg.team_id,
                page_id=p.page.page_id,
                parent_page_id=mid2.page.page_id,
                updated_by="x",
            )
            return "moved"
        except WikiPageDepthExceededError:
            return "move_rejected"

    async def _publish() -> str:
        try:
            await store.publish_proposal(
                team_id=pg.team_id,
                revision_id=proposal.revision_id,
                slug="too-deep2",
                approver_user_id="alice",
            )
            return "published"
        except WikiPageDepthExceededError:
            return "publish_rejected"

    moved_result, published_result = await asyncio.gather(_move_p_deeper(), _publish())

    assert not (moved_result == "moved" and published_result == "published")
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_publish_loses_to_a_reject_committed_between_its_read_and_write(
    pg: _Fixture,
) -> None:
    """WIKI-05's required invariant, proven under a forced interleaving: a
    `reject_stale_proposal` that commits strictly between `publish_proposal`'s
    own SELECT and its own write must beat the publish, and leave no partial
    write behind — not the page pointer, not the superseded mark on the
    revision it was about to replace.

    Edit-page path. `publish_proposal`'s SELECT still sees `status="proposed"`
    (the reject has not committed yet), so this is the window the SELECT-only
    guard could not close — only the CAS this fix added, on the write itself,
    can.
    """

    store = pg.store
    created = await store.create_page(
        team_id=pg.team_id,
        slug="race-edit",
        title="Race edit",
        content_md="v0",
        author_user_id="alice",
    )
    v0_id = created.page.current_revision_id
    assert v0_id is not None
    proposal = await store.create_proposal(
        team_id=pg.team_id,
        page_id=created.page.page_id,
        content_md="proposed edit",
        base_revision_id=v0_id,
        proposed_title=None,
        proposed_parent_page_id=None,
        author_user_id="alice",
        agent_instance_id="inst-1",
        session_id="sess-1",
    )

    reached = asyncio.Event()
    release = asyncio.Event()
    async with _pause_before_the_proposal_publish_write(reached, release):
        publish_task = asyncio.create_task(
            store.publish_proposal(
                team_id=pg.team_id,
                revision_id=proposal.revision_id,
                slug="race-edit-published",
                approver_user_id="bob",
            )
        )
        await reached.wait()

        # Publish already passed its own "still proposed" check. The reject
        # now runs and commits in a fully separate transaction, before
        # publish is allowed to write.
        assert await store.reject_stale_proposal(
            team_id=pg.team_id, revision_id=proposal.revision_id
        )

        release.set()
        with pytest.raises(WikiProposalNoLongerPendingError):
            await publish_task

    page = await store.get_page(pg.team_id, created.page.page_id)
    assert page is not None
    assert page.current_revision_id == v0_id
    v0 = await store.get_revision(pg.team_id, v0_id)
    assert v0 is not None
    assert v0.status == "published"  # never marked superseded by the loser
    revision = await store.get_revision(pg.team_id, proposal.revision_id)
    assert revision is not None
    assert revision.status == "rejected"  # never overwritten back to published
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_publish_loses_to_a_reject_of_a_new_page_proposal_creates_no_page(
    pg: _Fixture,
) -> None:
    """Same forced interleaving, the new-page path (§WIKI-04): a losing
    publish must not leave behind the page it was about to mint. Before this
    fix, `s.add(page_row)` had already been flushed by the time the stale
    `row.status = "published"` write landed, so a losing publish here used to
    commit a real page pointing at a revision the sweep had just rejected."""

    store = pg.store
    proposal = await store.create_proposal(
        team_id=pg.team_id,
        page_id=None,
        content_md="drafted by an agent",
        base_revision_id=None,
        proposed_title="Race new page",
        proposed_parent_page_id=None,
        author_user_id="alice",
        agent_instance_id="inst-1",
        session_id="sess-1",
    )

    reached = asyncio.Event()
    release = asyncio.Event()
    async with _pause_before_the_proposal_publish_write(reached, release):
        publish_task = asyncio.create_task(
            store.publish_proposal(
                team_id=pg.team_id,
                revision_id=proposal.revision_id,
                slug="race-new-page",
                approver_user_id="bob",
            )
        )
        await reached.wait()

        assert await store.reject_stale_proposal(
            team_id=pg.team_id, revision_id=proposal.revision_id
        )

        release.set()
        with pytest.raises(WikiProposalNoLongerPendingError):
            await publish_task

    assert await store.get_page(pg.team_id, proposal.page_id) is None
    revision = await store.get_revision(pg.team_id, proposal.revision_id)
    assert revision is not None
    assert revision.status == "rejected"
    await _assert_committed_tree_is_sound(store, pg.team_id)


@pytest.mark.asyncio
async def test_publish_loses_to_a_session_erasure_reject_committed_mid_transaction(
    pg: _Fixture,
) -> None:
    """Invariant 5: the same forced interleaving, `reject_proposals_for_session`
    in place of the lifecycle sweep — a session erased at the exact instant a
    human approves one of its still-pending proposals must not let the
    approval win over the erasure."""

    store = pg.store
    created = await store.create_page(
        team_id=pg.team_id,
        slug="race-session",
        title="Race session",
        content_md="v0",
        author_user_id="alice",
    )
    v0_id = created.page.current_revision_id
    assert v0_id is not None
    proposal = await store.create_proposal(
        team_id=pg.team_id,
        page_id=created.page.page_id,
        content_md="from a session about to be erased",
        base_revision_id=v0_id,
        proposed_title=None,
        proposed_parent_page_id=None,
        author_user_id="alice",
        agent_instance_id="inst-1",
        session_id="sess-erased",
    )

    reached = asyncio.Event()
    release = asyncio.Event()
    async with _pause_before_the_proposal_publish_write(reached, release):
        publish_task = asyncio.create_task(
            store.publish_proposal(
                team_id=pg.team_id,
                revision_id=proposal.revision_id,
                slug="race-session-published",
                approver_user_id="bob",
            )
        )
        await reached.wait()

        assert (
            await store.reject_proposals_for_session(
                team_id=pg.team_id, session_id="sess-erased"
            )
            == 1
        )

        release.set()
        with pytest.raises(WikiProposalNoLongerPendingError):
            await publish_task

    page = await store.get_page(pg.team_id, created.page.page_id)
    assert page is not None
    assert page.current_revision_id == v0_id
    await _assert_committed_tree_is_sound(store, pg.team_id)
