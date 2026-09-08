from __future__ import annotations

from pathlib import Path

import pytest
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.team_wiki.store import (
    TeamWikiStore,
    WikiPageConstraintError,
    WikiPageDepthExceededError,
    WikiPageHasChildrenError,
    WikiPageInvalidMoveError,
    WikiPageNotFoundError,
    WikiPageRecord,
    WikiPageRulesParentError,
    WikiRevisionConflictError,
    _child_depth_under,
    _is_descendant,
    _StaleBaseWrite,
    _subtree_height,
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
