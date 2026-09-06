from __future__ import annotations

from pathlib import Path

import pytest
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.team_wiki.store import (
    TeamWikiStore,
    WikiPageHasChildrenError,
    WikiRevisionConflictError,
    WikiSlugAlreadyExistsError,
)
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEAM_A = TeamId("team-a")
TEAM_B = TeamId("team-b")


async def _make_store(tmp_path: Path, name: str) -> tuple[TeamWikiStore, AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    return TeamWikiStore(engine=engine), engine


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
        with pytest.raises(WikiSlugAlreadyExistsError):
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
