from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.team_wiki_models import TeamWikiRevisionRow
from control_plane_backend.team_wiki.store import (
    RevisionCursor,
    TeamWikiStore,
    WikiPageConstraintError,
    WikiPageDepthExceededError,
    WikiPageHasChildrenError,
    WikiPageInvalidMoveError,
    WikiPageNotFoundError,
    WikiPageRecord,
    WikiPageRulesParentError,
    WikiPageWithContent,
    WikiRevisionConflictError,
    WikiRevisionRecord,
    _child_depth_under,
    _is_descendant,
    _StaleBaseWrite,
    _subtree_height,
)
from fred_core.common import TeamId
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEAM_A = TeamId("team-a")
TEAM_B = TeamId("team-b")


async def _make_store(tmp_path: Path, name: str) -> tuple[TeamWikiStore, AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    return TeamWikiStore(engine=engine), engine


async def _set_created_at(
    store: TeamWikiStore, revision_id: str, when: datetime
) -> None:
    """Test-only backdoor to force a tie or an out-of-order timestamp: real
    inserts always land at `_utcnow()`, so constructing either scenario
    through the public API alone is impractical."""

    async with store._sessions() as s, s.begin():  # noqa: SLF001
        await s.execute(
            update(TeamWikiRevisionRow)
            .where(TeamWikiRevisionRow.revision_id == revision_id)
            .values(created_at=when)
        )


@pytest.mark.asyncio
async def test_create_page_stores_page_and_first_revision(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "create.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="deployment",
            title="Deployment",
            content_md="# Deployment\n\nRun the thing.",
            author_user_id="alice",
        )
        assert created.revision is not None
        assert created.page.current_revision_id == created.revision.revision_id

        page = await store.get_page_by_slug(TEAM_A, "deployment")
        assert page is not None
        revision = await store.get_revision(TEAM_A, page.current_revision_id or "")
        assert revision is not None
        assert revision.content_md == "# Deployment\n\nRun the thing."
        assert revision.author_kind == "human"
        assert page.needs_review is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_edit_appends_a_revision_and_keeps_the_previous_one(
    tmp_path: Path,
) -> None:
    store, engine = await _make_store(tmp_path, "edit.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="first",
            author_user_id="alice",
        )
        first_id = created.page.current_revision_id
        assert first_id is not None

        second = await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="second",
            base_revision_id=first_id,
            author_user_id="bob",
        )

        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        assert page.current_revision_id == second.revision_id

        # The point of an append-only table: the previous text is still there.
        old = await store.get_revision(TEAM_A, first_id)
        assert old is not None
        assert old.content_md == "first"
        assert old.status == "superseded"

        history = await store.list_revisions(TEAM_A, created.page.page_id)
        assert [r.content_md for r in history] == ["second", "first"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_stale_base_is_refused_and_carries_the_current_content(
    tmp_path: Path,
) -> None:
    """Two editors open the same page; the second must not silently erase the
    first. The refusal carries what to rebase onto so the caller can redo it."""

    store, engine = await _make_store(tmp_path, "conflict.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="original",
            author_user_id="alice",
        )
        stale_base = created.page.current_revision_id
        assert stale_base is not None

        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="alice's edit",
            base_revision_id=stale_base,
            author_user_id="alice",
        )

        with pytest.raises(WikiRevisionConflictError) as caught:
            await store.publish_revision(
                team_id=TEAM_A,
                page_id=created.page.page_id,
                content_md="bob's edit",
                base_revision_id=stale_base,
                author_user_id="bob",
            )
        assert caught.value.current_content_md == "alice's edit"

        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        current = await store.get_revision(TEAM_A, page.current_revision_id or "")
        assert current is not None
        assert current.content_md == "alice's edit"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_slug_is_unique_within_a_team_but_free_across_teams(
    tmp_path: Path,
) -> None:
    store, engine = await _make_store(tmp_path, "slug.sqlite3")
    try:
        await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="a", author_user_id="alice"
        )
        with pytest.raises(WikiPageConstraintError):
            await store.create_page(
                team_id=TEAM_A,
                slug="p",
                title="P again",
                content_md="b",
                author_user_id="alice",
            )
        # Another team using the same slug is not a conflict — one table holds
        # every team's pages, and team_id is the boundary.
        other = await store.create_page(
            team_id=TEAM_B, slug="p", title="P", content_md="b", author_user_id="bob"
        )
        assert other.page.team_id == TEAM_B
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_one_team_never_sees_another_team_s_pages(tmp_path: Path) -> None:
    """The tenant boundary. Every read filters on team_id, including reads
    addressed by an id the caller could have obtained elsewhere."""

    store, engine = await _make_store(tmp_path, "isolation.sqlite3")
    try:
        a = await store.create_page(
            team_id=TEAM_A,
            slug="secret",
            title="Secret",
            content_md="team a only",
            author_user_id="alice",
        )
        await store.create_page(
            team_id=TEAM_B,
            slug="other",
            title="Other",
            content_md="b",
            author_user_id="bob",
        )

        assert [p.slug for p in await store.list_pages(TEAM_A)] == ["secret"]
        assert await store.get_page_by_slug(TEAM_B, "secret") is None
        # Knowing team A's page id is not enough to read it as team B.
        assert await store.get_page(TEAM_B, a.page.page_id) is None
        assert (
            await store.get_revision(TEAM_B, a.page.current_revision_id or "") is None
        )
        assert await store.list_revisions(TEAM_B, a.page.page_id) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_agent_revision_marks_the_page_for_review(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "review.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="human text",
            author_user_id="alice",
        )
        assert created.page.needs_review is False

        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="agent text",
            base_revision_id=created.page.current_revision_id,
            author_user_id="alice",
            author_kind="agent",
            agent_instance_id="inst-1",
            session_id="sess-1",
        )
        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        assert page.needs_review is True

        # A human editing the page IS the review.
        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="human correction",
            base_revision_id=page.current_revision_id,
            author_user_id="alice",
        )
        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        assert page.needs_review is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clearing_the_review_mark_records_the_validation(tmp_path: Path) -> None:
    """Validating an agent's page is its own event, and not an edit.

    Two things used to be lost: who validated (nothing recorded it at all), and
    who wrote (the page's `updated_by` was overwritten with the reviewer).
    """
    store, engine = await _make_store(tmp_path, "review-stamp.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="human text",
            author_user_id="alice",
        )
        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="agent text",
            base_revision_id=created.page.current_revision_id,
            author_user_id="alice",
            author_kind="agent",
            agent_instance_id="inst-1",
        )
        written = await store.get_page(TEAM_A, created.page.page_id)
        assert written is not None

        await store.set_needs_review(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            needs_review=False,
            reviewed_by="bob",
        )

        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        assert page.needs_review is False
        # Bob read the page; he did not write it.
        assert page.updated_by == "alice"
        assert page.updated_at == written.updated_at

        revisions = await store.list_revisions(TEAM_A, created.page.page_id)
        current = next(
            r for r in revisions if r.revision_id == page.current_revision_id
        )
        assert current.reviewed_by == "bob"
        assert current.reviewed_at is not None

        # Re-flagging withdraws the validation — the same text is under review
        # again, so the old approval must not still stand against it.
        await store.set_needs_review(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            needs_review=True,
            reviewed_by="bob",
        )
        revisions = await store.list_revisions(TEAM_A, created.page.page_id)
        current = next(
            r for r in revisions if r.revision_id == page.current_revision_id
        )
        assert current.reviewed_at is None
        assert current.reviewed_by is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_a_page_with_children_is_refused(tmp_path: Path) -> None:
    """Revision history cannot undo a lost subtree — the pages themselves would
    be gone — so the delete refuses rather than cascading."""

    store, engine = await _make_store(tmp_path, "children.sqlite3")
    try:
        parent = await store.create_page(
            team_id=TEAM_A,
            slug="parent",
            title="Parent",
            content_md="",
            author_user_id="alice",
        )
        await store.create_page(
            team_id=TEAM_A,
            slug="child",
            title="Child",
            content_md="",
            parent_page_id=parent.page.page_id,
            author_user_id="alice",
        )
        with pytest.raises(WikiPageHasChildrenError):
            await store.delete_page(team_id=TEAM_A, page_id=parent.page.page_id)
        assert await store.get_page(TEAM_A, parent.page.page_id) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publish_proposal_refused_when_the_page_moved_since_the_read(
    tmp_path: Path,
) -> None:
    """Read A, propose from A, someone else publishes B, publish the proposal:
    the proposal's base (A) no longer matches the page's current revision (B),
    so the approval must not silently overwrite B."""

    store, engine = await _make_store(tmp_path, "propose-stale.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="A",
            author_user_id="alice",
        )
        revision_a = created.page.current_revision_id
        assert revision_a is not None

        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="agent's edit of A",
            base_revision_id=revision_a,
            proposed_title=None,
            proposed_parent_page_id=None,
            author_user_id="alice",
            agent_instance_id="inst-1",
            session_id="sess-1",
        )

        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="B",
            base_revision_id=revision_a,
            author_user_id="bob",
        )

        with pytest.raises(_StaleBaseWrite):
            await store.publish_proposal(
                team_id=TEAM_A,
                revision_id=proposal.revision_id,
                slug="p",
                approver_user_id="alice",
            )

        page = await store.get_page(TEAM_A, created.page.page_id)
        assert page is not None
        current = await store.get_revision(TEAM_A, page.current_revision_id or "")
        assert current is not None
        assert current.content_md == "B"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publish_proposal_succeeds_when_nothing_moved(tmp_path: Path) -> None:
    """Read A, propose from A, publish the proposal with nothing else having
    written in between: the happy path this correction must not break."""

    store, engine = await _make_store(tmp_path, "propose-ok.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="A",
            author_user_id="alice",
        )
        revision_a = created.page.current_revision_id
        assert revision_a is not None

        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="agent's edit of A",
            base_revision_id=revision_a,
            proposed_title=None,
            proposed_parent_page_id=None,
            author_user_id="alice",
            agent_instance_id="inst-1",
            session_id="sess-1",
        )

        page = await store.publish_proposal(
            team_id=TEAM_A,
            revision_id=proposal.revision_id,
            slug="p",
            approver_user_id="alice",
        )

        assert page.current_revision_id == proposal.revision_id
        current = await store.get_revision(TEAM_A, page.current_revision_id or "")
        assert current is not None
        assert current.content_md == "agent's edit of A"
        assert current.status == "published"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_a_leaf_removes_its_revisions(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "delete.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="one",
            author_user_id="alice",
        )
        await store.publish_revision(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            content_md="two",
            base_revision_id=created.page.current_revision_id,
            author_user_id="alice",
        )
        await store.delete_page(team_id=TEAM_A, page_id=created.page.page_id)

        assert await store.get_page(TEAM_A, created.page.page_id) is None
        assert await store.list_revisions(TEAM_A, created.page.page_id) == []
    finally:
        await engine.dispose()


# ── history pagination (WIKI-05) ──────────────────────────────────────────────


async def _add_revisions(
    store: TeamWikiStore, page_id: str, base: str | None, contents: list[str]
) -> list[str]:
    """Publishes `contents` in order, each on top of the last. Returns every
    revision id created, oldest first."""

    ids: list[str] = []
    for content_md in contents:
        revision = await store.publish_revision(
            team_id=TEAM_A,
            page_id=page_id,
            content_md=content_md,
            base_revision_id=base,
            author_user_id="alice",
        )
        base = revision.revision_id
        ids.append(revision.revision_id)
    return ids


def _cursor_after(revision: WikiRevisionRecord) -> RevisionCursor:
    """The keyset position just past `revision` — every real row has a
    `created_at` once persisted; this is what narrows the type for the
    `RevisionCursor` it builds."""

    assert revision.created_at is not None
    return RevisionCursor(
        created_at=revision.created_at, revision_id=revision.revision_id
    )


def _first_revision_id(page: WikiPageWithContent) -> str:
    """`create_page` always mints a first revision — `current_revision_id` is
    only `None` in the ORM's own type for the instant between the page and
    revision inserts, which this store method never observes."""

    revision_id = page.page.current_revision_id
    assert revision_id is not None
    return revision_id


@pytest.mark.asyncio
async def test_list_revisions_bounds_the_query_in_sql(tmp_path: Path) -> None:
    """Proof the LIMIT lives in the SQL, not a Python slice after loading
    everything: reverting to that would still return the right COUNT here,
    which is why this inspects the emitted statement instead of only len()."""

    store, engine = await _make_store(tmp_path, "bounded.sqlite3")
    captured: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        captured.append(statement)

    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        await _add_revisions(
            store,
            page_id,
            created.page.current_revision_id,
            [f"v{i}" for i in range(1, 6)],
        )

        captured.clear()
        revisions = await store.list_revisions(TEAM_A, page_id, limit=2)
        assert len(revisions) == 2

        selects = [
            sql
            for sql in captured
            if "team_wiki_revisions" in sql and sql.strip().upper().startswith("SELECT")
        ]
        assert selects, "expected a SELECT against team_wiki_revisions"
        assert "LIMIT" in selects[-1].upper()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_revisions_walks_more_than_a_page_without_gaps_or_duplicates(
    tmp_path: Path,
) -> None:
    store, engine = await _make_store(tmp_path, "walk.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        total = 7
        v0_id = _first_revision_id(created)
        all_ids = [v0_id] + await _add_revisions(
            store, page_id, v0_id, [f"v{i}" for i in range(1, total)]
        )

        walked: list[str] = []
        cursor: RevisionCursor | None = None
        page_size = 3
        for _ in range(10):  # generous bound, never an endless loop
            page = await store.list_revisions(
                TEAM_A, page_id, limit=page_size, before=cursor
            )
            if not page:
                break
            walked.extend(r.revision_id for r in page)
            cursor = _cursor_after(page[-1])
            if len(page) < page_size:
                break

        assert walked == list(reversed(all_ids))
        assert len(set(walked)) == total
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_revisions_cursor_is_exact_under_tied_timestamps(
    tmp_path: Path,
) -> None:
    """Several revisions sharing one `created_at` is ordinary (an edit then a
    restore inside the same second) — the walk must still be exact, broken
    only by `revision_id`."""

    store, engine = await _make_store(tmp_path, "ties.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = _first_revision_id(created)
        all_ids = [v0_id] + await _add_revisions(
            store, page_id, v0_id, [f"v{i}" for i in range(1, 5)]
        )

        same_instant = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for revision_id in all_ids:
            await _set_created_at(store, revision_id, same_instant)

        walked: list[str] = []
        cursor: RevisionCursor | None = None
        for _ in range(10):
            page = await store.list_revisions(TEAM_A, page_id, limit=1, before=cursor)
            if not page:
                break
            walked.append(page[0].revision_id)
            cursor = _cursor_after(page[0])

        assert sorted(walked) == sorted(all_ids)
        assert len(set(walked)) == len(all_ids)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_write_landing_mid_walk_does_not_shift_an_older_page(
    tmp_path: Path,
) -> None:
    """New revisions land only at the newest end. A walk already anchored on
    an older cursor must be unaffected by one appearing while it is in
    progress — unlike an offset, which every such insert would shift."""

    store, engine = await _make_store(tmp_path, "midwalk.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = _first_revision_id(created)
        ids = [v0_id] + await _add_revisions(store, page_id, v0_id, ["v1", "v2", "v3"])

        first_page = await store.list_revisions(TEAM_A, page_id, limit=2)
        cursor = _cursor_after(first_page[-1])

        # A concurrent write lands while the reader is mid-walk.
        await store.publish_revision(
            team_id=TEAM_A,
            page_id=page_id,
            content_md="v-concurrent",
            base_revision_id=ids[-1],
            author_user_id="bob",
        )

        second_page = await store.list_revisions(
            TEAM_A, page_id, limit=2, before=cursor
        )
        first_seen = {r.revision_id for r in first_page}
        second_seen = {r.revision_id for r in second_page}
        assert not (first_seen & second_seen)
        assert all(r.content_md != "v-concurrent" for r in second_page)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sort_columns_never_change_after_insert(tmp_path: Path) -> None:
    """`created_at` and `revision_id` are the keyset's watermark — if either
    could change after insert, a cursor anchored on an earlier read would no
    longer identify the same boundary."""

    store, engine = await _make_store(tmp_path, "stable_sort.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A,
            slug="p",
            title="P",
            content_md="v0",
            author_user_id="alice",
            author_kind="agent",
        )
        revision_id = created.page.current_revision_id
        assert revision_id is not None
        before = await store.get_revision(TEAM_A, revision_id)
        assert before is not None

        await store.set_needs_review(
            team_id=TEAM_A,
            page_id=created.page.page_id,
            needs_review=False,
            reviewed_by="bob",
        )

        after = await store.get_revision(TEAM_A, revision_id)
        assert after is not None
        assert after.created_at == before.created_at
        assert after.revision_id == before.revision_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publishing_a_proposal_never_backdates_into_an_already_read_page(
    tmp_path: Path,
) -> None:
    """A pending proposal's `created_at` is proposal time, not approval time —
    in principle a later-approved revision could surface "behind" a cursor a
    reader had already established. In practice this is closed by
    `publish_proposal`'s own base-revision guard (CONTROL-PLANE-PRODUCT-
    CONTRACT.md §49): a proposal can only be approved while its base is still
    the page's current revision, i.e. nothing else was published since — so
    the approved revision is always the newest thing on the page, never older
    than anything a reader has already paged past.
    """

    store, engine = await _make_store(tmp_path, "proposal_ordering.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = created.page.current_revision_id
        assert v0_id is not None

        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=page_id,
            content_md="proposed edit",
            base_revision_id=v0_id,
            proposed_title=None,
            proposed_parent_page_id=None,
            author_user_id="alice",
            agent_instance_id=None,
            session_id=None,
        )

        # A reader walks the page's history to its current end...
        first_page = await store.list_revisions(TEAM_A, page_id, limit=10)
        assert [r.revision_id for r in first_page] == [v0_id]
        cursor = _cursor_after(first_page[-1])

        # ...then the pending proposal is approved, with nothing else having
        # touched the page in between: its base is still current, so this
        # succeeds rather than conflicting.
        await store.publish_proposal(
            team_id=TEAM_A,
            revision_id=proposal.revision_id,
            slug="unused",
            approver_user_id="bob",
        )

        # It shows up at the very front of a fresh read...
        fresh = await store.list_revisions(TEAM_A, page_id, limit=10)
        assert fresh[0].revision_id == proposal.revision_id

        # ...and never behind the reader's already-established cursor.
        continued = await store.list_revisions(TEAM_A, page_id, limit=10, before=cursor)
        assert proposal.revision_id not in {r.revision_id for r in continued}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publishing_a_stale_proposal_is_refused_not_silently_backdated(
    tmp_path: Path,
) -> None:
    """The other half of the guard above: if something DID land on the page
    after the proposal was drafted, approving it is refused rather than
    quietly inserting an old-timestamped revision into already-read history.
    """

    store, engine = await _make_store(tmp_path, "proposal_stale.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = created.page.current_revision_id
        assert v0_id is not None

        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=page_id,
            content_md="proposed edit",
            base_revision_id=v0_id,
            proposed_title=None,
            proposed_parent_page_id=None,
            author_user_id="alice",
            agent_instance_id=None,
            session_id=None,
        )
        await store.publish_revision(
            team_id=TEAM_A,
            page_id=page_id,
            content_md="v1",
            base_revision_id=v0_id,
            author_user_id="alice",
        )

        with pytest.raises(_StaleBaseWrite):
            await store.publish_proposal(
                team_id=TEAM_A,
                revision_id=proposal.revision_id,
                slug="unused",
                approver_user_id="bob",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_revisions_excludes_proposals_from_the_page_and_the_walk(
    tmp_path: Path,
) -> None:
    """A pending proposal must not consume a slot in the page, nor shift where
    the cursor lands — it is invisible to the query, not merely hidden by the
    caller after the fact."""

    store, engine = await _make_store(tmp_path, "proposals_excluded.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = created.page.current_revision_id
        assert v0_id is not None
        ids = [v0_id] + await _add_revisions(store, page_id, v0_id, ["v1", "v2"])

        await store.create_proposal(
            team_id=TEAM_A,
            page_id=page_id,
            content_md="pending",
            base_revision_id=ids[-1],
            proposed_title=None,
            proposed_parent_page_id=None,
            author_user_id="alice",
            agent_instance_id=None,
            session_id=None,
        )

        page = await store.list_revisions(TEAM_A, page_id, limit=2)
        assert [r.revision_id for r in page] == list(reversed(ids))[:2]
        assert all(r.content_md != "pending" for r in page)

        cursor = _cursor_after(page[-1])
        rest = await store.list_revisions(TEAM_A, page_id, limit=2, before=cursor)
        assert [r.revision_id for r in rest] == [ids[0]]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_older_paginated_revision_can_be_restored(tmp_path: Path) -> None:
    """Acceptance: a revision reached only through `before` (not on the first
    page) is a perfectly ordinary revision to restore — `restore` addresses a
    revision by id, never by its position in a page."""

    store, engine = await _make_store(tmp_path, "restore_paginated.sqlite3")
    try:
        created = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="v0", author_user_id="alice"
        )
        page_id = created.page.page_id
        v0_id = _first_revision_id(created)
        ids = [v0_id] + await _add_revisions(store, page_id, v0_id, ["v1", "v2"])

        first_page = await store.list_revisions(TEAM_A, page_id, limit=1)
        cursor = _cursor_after(first_page[-1])
        older_page = await store.list_revisions(TEAM_A, page_id, limit=1, before=cursor)
        target = older_page[0]
        assert target.revision_id == ids[1]  # "v1", reached only via `before`

        page = await store.get_page(TEAM_A, page_id)
        assert page is not None
        restored = await store.publish_revision(
            team_id=TEAM_A,
            page_id=page_id,
            content_md=target.content_md,
            base_revision_id=page.current_revision_id,
            author_user_id="alice",
        )

        current = await store.get_page(TEAM_A, page_id)
        assert current is not None
        assert current.current_revision_id == restored.revision_id
        assert restored.content_md == "v1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_cursor_from_one_team_does_not_leak_another_teams_page(
    tmp_path: Path,
) -> None:
    """The cursor is a position within one page's history, never a bypass for
    the team/page scope the store filters on independently."""

    store, engine = await _make_store(tmp_path, "cursor_cross_team.sqlite3")
    try:
        a = await store.create_page(
            team_id=TEAM_A, slug="p", title="P", content_md="a0", author_user_id="alice"
        )
        b = await store.create_page(
            team_id=TEAM_B, slug="p", title="P", content_md="b0", author_user_id="carol"
        )
        revision = await store.get_revision(TEAM_A, a.page.current_revision_id or "")
        assert revision is not None
        assert revision.created_at is not None
        cursor = RevisionCursor(
            created_at=revision.created_at + timedelta(seconds=10),
            revision_id="f" * 32,
        )

        result = await store.list_revisions(
            TEAM_B, b.page.page_id, limit=10, before=cursor
        )
        assert [r.revision_id for r in result] == [_first_revision_id(b)]
    finally:
        await engine.dispose()


# ── pure tree-shape helpers ──────────────────────────────────────────────────
#
# The structural validators every writer below relies on. Moved here from
# `test_team_wiki_service.py` along with the functions themselves: they back
# the checks that now run inside `_structural_lock`, not the service.


def _page(page_id: str, parent: str | None) -> WikiPageRecord:
    return WikiPageRecord(
        page_id=page_id,
        team_id=TEAM_A,
        slug=page_id,
        title=page_id,
        parent_page_id=parent,
        current_revision_id=f"rev-{page_id}",
    )


def test_child_depth_is_the_depth_the_child_would_sit_at() -> None:
    """A root page is depth 0, so a child of a root is 1. The helper is named
    for what it returns: read as "depth of the parent", the cap lands a tier
    out."""

    pages = {"a": _page("a", None), "b": _page("b", "a"), "c": _page("c", "b")}
    assert _child_depth_under(pages, None) == 0
    assert _child_depth_under(pages, "a") == 1
    assert _child_depth_under(pages, "c") == 3


def test_child_depth_terminates_on_a_cycle() -> None:
    """A cycle should be impossible, but a bounded walk means a corrupted row
    cannot hang a request while someone works out why."""

    pages = {"a": _page("a", "b"), "b": _page("b", "a")}
    assert _child_depth_under(pages, "a") <= 10


def test_subtree_height_is_zero_for_a_leaf_and_counts_levels_below() -> None:
    pages = {
        "root": _page("root", None),
        "child": _page("child", "root"),
        "grandchild": _page("grandchild", "child"),
    }
    assert _subtree_height(pages, "grandchild") == 0
    assert _subtree_height(pages, "child") == 1
    assert _subtree_height(pages, "root") == 2


def test_is_descendant_detects_the_move_that_would_detach_a_subtree() -> None:
    pages = {
        "root": _page("root", None),
        "child": _page("child", "root"),
        "grandchild": _page("grandchild", "child"),
    }
    assert _is_descendant(pages, "grandchild", "root") is True
    assert _is_descendant(pages, "root", "grandchild") is False


def test_is_descendant_is_reflexive_and_catches_a_self_parent() -> None:
    """A page named as its own parent is the degenerate cycle: `candidate_id`
    equal to `ancestor_id` must read as true without a special case."""

    pages = {"p": _page("p", None)}
    assert _is_descendant(pages, "p", "p") is True


# ── structural validation, offline (SQLite: the lock is a documented no-op —
# these prove the checks fire on a single writer, not the serialization
# guarantee under concurrency; see the Postgres integration suite for that) ──


@pytest.mark.asyncio
async def test_create_page_under_a_nonexistent_parent_is_refused(
    tmp_path: Path,
) -> None:
    store, engine = await _make_store(tmp_path, "create-no-parent.sqlite3")
    try:
        with pytest.raises(WikiPageNotFoundError):
            await store.create_page(
                team_id=TEAM_A,
                slug="p",
                title="P",
                content_md="",
                parent_page_id="does-not-exist",
                author_user_id="alice",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_page_under_the_rules_page_is_refused(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "create-under-rules.sqlite3")
    try:
        rules = await store.create_page(
            team_id=TEAM_A,
            slug="__rules__",
            title="Rules",
            content_md="",
            kind="rules",
            author_user_id="alice",
        )
        with pytest.raises(WikiPageRulesParentError):
            await store.create_page(
                team_id=TEAM_A,
                slug="p",
                title="P",
                content_md="",
                parent_page_id=rules.page.page_id,
                author_user_id="alice",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_page_past_the_depth_cap_is_refused(tmp_path: Path) -> None:
    """MAX_PAGE_DEPTH is 3: root `a`(0)-`b`(1)-`c`(2)-`d`(3) is the deepest legal
    chain — `d` itself is fine — so a child of `d` would sit at 4."""

    store, engine = await _make_store(tmp_path, "create-too-deep.sqlite3")
    try:
        a = await store.create_page(
            team_id=TEAM_A, slug="a", title="a", content_md="", author_user_id="x"
        )
        b = await store.create_page(
            team_id=TEAM_A,
            slug="b",
            title="b",
            content_md="",
            parent_page_id=a.page.page_id,
            author_user_id="x",
        )
        c = await store.create_page(
            team_id=TEAM_A,
            slug="c",
            title="c",
            content_md="",
            parent_page_id=b.page.page_id,
            author_user_id="x",
        )
        d = await store.create_page(
            team_id=TEAM_A,
            slug="d",
            title="d",
            content_md="",
            parent_page_id=c.page.page_id,
            author_user_id="x",
        )
        with pytest.raises(WikiPageDepthExceededError):
            await store.create_page(
                team_id=TEAM_A,
                slug="e",
                title="e",
                content_md="",
                parent_page_id=d.page.page_id,
                author_user_id="x",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_moving_a_page_under_its_own_child_is_refused(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "move-under-child.sqlite3")
    try:
        root = await store.create_page(
            team_id=TEAM_A, slug="root", title="root", content_md="", author_user_id="x"
        )
        child = await store.create_page(
            team_id=TEAM_A,
            slug="child",
            title="child",
            content_md="",
            parent_page_id=root.page.page_id,
            author_user_id="x",
        )
        with pytest.raises(WikiPageInvalidMoveError):
            await store.update_page_metadata(
                team_id=TEAM_A,
                page_id=root.page.page_id,
                parent_page_id=child.page.page_id,
                updated_by="x",
            )
        # Refused, not partially applied.
        untouched = await store.get_page(TEAM_A, root.page.page_id)
        assert untouched is not None
        assert untouched.parent_page_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_page_cannot_be_moved_under_itself(tmp_path: Path) -> None:
    store, engine = await _make_store(tmp_path, "move-self.sqlite3")
    try:
        p = await store.create_page(
            team_id=TEAM_A, slug="p", title="p", content_md="", author_user_id="x"
        )
        with pytest.raises(WikiPageInvalidMoveError):
            await store.update_page_metadata(
                team_id=TEAM_A,
                page_id=p.page.page_id,
                parent_page_id=p.page.page_id,
                updated_by="x",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_move_accounts_for_the_subtree_it_carries(tmp_path: Path) -> None:
    """Checking only the destination's depth lets create-then-move defeat the
    cap: the pages are shallow one at a time, deep once attached. `a` carries
    `b` and `c` with it (height 2); `dest-child` already sits at depth 2, so
    landing `a` there would push `c` to depth 4."""

    store, engine = await _make_store(tmp_path, "move-subtree.sqlite3")
    try:
        a = await store.create_page(
            team_id=TEAM_A, slug="a", title="a", content_md="", author_user_id="x"
        )
        b = await store.create_page(
            team_id=TEAM_A,
            slug="b",
            title="b",
            content_md="",
            parent_page_id=a.page.page_id,
            author_user_id="x",
        )
        await store.create_page(
            team_id=TEAM_A,
            slug="c",
            title="c",
            content_md="",
            parent_page_id=b.page.page_id,
            author_user_id="x",
        )
        dest = await store.create_page(
            team_id=TEAM_A, slug="dest", title="dest", content_md="", author_user_id="x"
        )
        dest_child = await store.create_page(
            team_id=TEAM_A,
            slug="dest-child",
            title="dest-child",
            content_md="",
            parent_page_id=dest.page.page_id,
            author_user_id="x",
        )

        with pytest.raises(WikiPageDepthExceededError):
            await store.update_page_metadata(
                team_id=TEAM_A,
                page_id=a.page.page_id,
                parent_page_id=dest_child.page.page_id,
                updated_by="x",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_rename_with_no_parent_change_is_unaffected_by_the_structural_checks(
    tmp_path: Path,
) -> None:
    """A plain rename still takes the structural lock (one discipline for
    every writer that can touch this row), but with no parent in play the
    cycle/depth/rules checks are no-ops."""

    store, engine = await _make_store(tmp_path, "rename-only.sqlite3")
    try:
        p = await store.create_page(
            team_id=TEAM_A, slug="p", title="Old", content_md="", author_user_id="x"
        )
        updated = await store.update_page_metadata(
            team_id=TEAM_A, page_id=p.page.page_id, title="New", updated_by="x"
        )
        assert updated.title == "New"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publishing_a_new_page_proposal_falls_back_to_root_when_its_parent_is_gone(
    tmp_path: Path,
) -> None:
    """The parent named when the proposal was written may since have been
    deleted. Publishing at the root rather than dangling is the documented
    behaviour (§WIKI-04) — this proves it still holds once the resolution
    moved inside the structural lock."""

    store, engine = await _make_store(tmp_path, "proposal-parent-gone.sqlite3")
    try:
        parent = await store.create_page(
            team_id=TEAM_A,
            slug="parent",
            title="Parent",
            content_md="",
            author_user_id="alice",
        )
        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=None,
            content_md="drafted by an agent",
            base_revision_id=None,
            proposed_title="New page",
            proposed_parent_page_id=parent.page.page_id,
            author_user_id="alice",
            agent_instance_id="inst-1",
            session_id="sess-1",
        )
        # Nothing points at the proposal yet, so the parent can be deleted.
        await store.delete_page(team_id=TEAM_A, page_id=parent.page.page_id)

        page = await store.publish_proposal(
            team_id=TEAM_A,
            revision_id=proposal.revision_id,
            slug="new-page",
            approver_user_id="alice",
        )

        assert page.parent_page_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publishing_a_new_page_proposal_past_the_depth_cap_is_refused(
    tmp_path: Path,
) -> None:
    """The named parent (`p`) is still there, but a second structural writer —
    a plain move, legal on its own — pushed `p` itself deeper while the
    proposal waited for a human. Publishing the proposal re-reads `p`'s depth
    as it stands now, not as it stood when the proposal was written, and
    refuses rather than land its new page at depth 4."""

    store, engine = await _make_store(tmp_path, "proposal-too-deep.sqlite3")
    try:
        p = await store.create_page(
            team_id=TEAM_A, slug="p", title="p", content_md="", author_user_id="x"
        )
        proposal = await store.create_proposal(
            team_id=TEAM_A,
            page_id=None,
            content_md="drafted by an agent",
            base_revision_id=None,
            proposed_title="Too deep",
            proposed_parent_page_id=p.page.page_id,
            author_user_id="alice",
            agent_instance_id="inst-1",
            session_id="sess-1",
        )

        # An independent chain reaching depth 2, unrelated to `p`.
        anchor = await store.create_page(
            team_id=TEAM_A,
            slug="anchor",
            title="anchor",
            content_md="",
            author_user_id="x",
        )
        mid1 = await store.create_page(
            team_id=TEAM_A,
            slug="mid1",
            title="mid1",
            content_md="",
            parent_page_id=anchor.page.page_id,
            author_user_id="x",
        )
        mid2 = await store.create_page(
            team_id=TEAM_A,
            slug="mid2",
            title="mid2",
            content_md="",
            parent_page_id=mid1.page.page_id,
            author_user_id="x",
        )

        # `p` has no children of its own yet (the proposal hasn't published),
        # so moving it under `mid2` (depth 2) is itself legal: `p` lands at
        # depth 3, exactly the cap.
        await store.update_page_metadata(
            team_id=TEAM_A,
            page_id=p.page.page_id,
            parent_page_id=mid2.page.page_id,
            updated_by="x",
        )

        with pytest.raises(WikiPageDepthExceededError):
            await store.publish_proposal(
                team_id=TEAM_A,
                revision_id=proposal.revision_id,
                slug="too-deep",
                approver_user_id="alice",
            )
    finally:
        await engine.dispose()
