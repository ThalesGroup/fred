from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import advisory_lock_key, make_session_factory, use_session
from sqlalchemy import and_, delete, or_, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.team_wiki_models import (
    MAX_PAGE_DEPTH,
    MAX_REVISION_PAGE_SIZE,
    TeamWikiPageRow,
    TeamWikiRevisionRow,
)


def _utcnow() -> datetime:
    """One timezone-aware UTC timestamp.

    Microseconds are KEPT, unlike the other control-plane stores which truncate
    them for display tidiness: this timestamp orders a page's history, and two
    revisions of one page within the same second are ordinary (an edit then a
    restore, a correction right after a save). Truncating made that order
    arbitrary.
    """

    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class WikiPageNotFoundError(Exception):
    """No page with that id or slug in this team."""


class WikiPageConstraintError(Exception):
    """A page row collided with another: the same slug, or a sibling already
    carrying the same title. Both are refused by a unique index, and both reach
    the caller as a 409 — the service checks each before writing, so this is
    the concurrent-write path rather than the ordinary one."""


class _StaleBaseWrite(Exception):
    """Internal: the conditional UPDATE matched no row. Raised to roll the
    transaction back before the current state is read, so the payload cannot be
    the stale row this transaction opened on."""


class WikiRevisionConflictError(Exception):
    """The page moved on since the author read it.

    Carries the current content so the caller can redo its edit against it
    rather than being told only that it failed.
    """

    def __init__(self, current_revision_id: str, current_content_md: str) -> None:
        super().__init__("This page has changed since the edit was prepared.")
        self.current_revision_id = current_revision_id
        self.current_content_md = current_content_md


class WikiProposalNoLongerPendingError(Exception):
    """`publish_proposal`'s own CAS matched no row: a reject (decline, sweep,
    or session erasure) committed `status="rejected"` after this transaction
    read the row as `proposed` but before this transaction's own write.

    Distinct from `_StaleBaseWrite`, which is about the PAGE's pointer moving
    under an edit — this is about the proposal row's status losing a race, and
    is reported the same way a proposal found already rejected at the initial
    lookup is: "no longer pending", not a page conflict.
    """


class WikiPageHasChildrenError(Exception):
    """Refusing to delete a page that still has children."""


class WikiPageDepthExceededError(Exception):
    """A create, move, or proposal publication would land past MAX_PAGE_DEPTH."""


class WikiPageInvalidMoveError(Exception):
    """A move would place a page under itself or one of its own descendants."""


class WikiPageRulesParentError(Exception):
    """The named parent is the rules page, which may not have children."""


@dataclass
class WikiPageRecord:
    """In-memory projection of one ``team_wiki_pages`` row."""

    page_id: str
    team_id: TeamId
    slug: str
    title: str
    kind: str = "page"
    parent_page_id: str | None = None
    current_revision_id: str | None = None
    needs_review: bool = False
    position: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


@dataclass
class WikiRevisionRecord:
    """In-memory projection of one ``team_wiki_revisions`` row."""

    revision_id: str
    page_id: str
    team_id: TeamId
    content_md: str
    status: str = "published"
    base_revision_id: str | None = None
    author_user_id: str = ""
    author_kind: str = "human"
    agent_instance_id: str | None = None
    session_id: str | None = None
    created_at: datetime | None = None
    # Set only on a proposal for a page that does not exist yet (WIKI-04).
    proposed_title: str | None = None
    proposed_parent_page_id: str | None = None
    # Who cleared the page's review mark while this revision was published.
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


@dataclass(frozen=True)
class RevisionCursor:
    """Keyset position in one page's history: the `(created_at, revision_id)`
    of the last revision the caller already has, exclusive.

    Not an offset. History is only ever appended to at the newest end, and a
    revision's own `(created_at, revision_id)` never changes after insert, so
    walking strictly older than a fixed watermark is stable under concurrent
    writes in a way a row-count offset is not — a write landing while the
    caller is mid-walk cannot shift this boundary the way it would shift
    every offset past it.
    """

    created_at: datetime
    revision_id: str


@dataclass(frozen=True)
class StaleProposalCandidate:
    """One `status="proposed"` row old enough for the lifecycle sweep to act
    on — just enough to log and to run the conditional reject against
    (§49). Not a `WikiRevisionRecord`: the sweep never needs the content."""

    revision_id: str
    team_id: TeamId
    page_id: str
    created_at: datetime


@dataclass
class WikiPageWithContent:
    """One page and the content currently published on it."""

    page: WikiPageRecord
    revision: WikiRevisionRecord | None = None
    children_ids: list[str] = field(default_factory=list)


def _to_page(row: TeamWikiPageRow) -> WikiPageRecord:
    return WikiPageRecord(
        page_id=row.page_id,
        team_id=TeamId(row.team_id),
        slug=row.slug,
        title=row.title,
        kind=row.kind,
        parent_page_id=row.parent_page_id,
        current_revision_id=row.current_revision_id,
        needs_review=row.needs_review,
        position=row.position,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _to_revision(row: TeamWikiRevisionRow) -> WikiRevisionRecord:
    return WikiRevisionRecord(
        revision_id=row.revision_id,
        page_id=row.page_id,
        team_id=TeamId(row.team_id),
        content_md=row.content_md,
        status=row.status,
        base_revision_id=row.base_revision_id,
        author_user_id=row.author_user_id,
        author_kind=row.author_kind,
        agent_instance_id=row.agent_instance_id,
        session_id=row.session_id,
        created_at=row.created_at,
        proposed_title=row.proposed_title,
        proposed_parent_page_id=row.proposed_parent_page_id,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
    )


def _child_depth_under(
    pages: dict[str, WikiPageRecord], parent_page_id: str | None
) -> int:
    """The depth a new child of `parent_page_id` would sit at.

    A root page is depth 0, so a child of a root sits at 1, and `None` — no
    parent — is 0. Named for what it returns: called it "depth of", the caller
    reads it as the parent's own depth and the cap ends up one tier out.

    The walk is bounded so a cycle left by an older bug cannot spin here.
    """

    depth = 0
    cursor = parent_page_id
    while cursor is not None and depth <= MAX_PAGE_DEPTH + 2:
        parent = pages.get(cursor)
        if parent is None:
            break
        cursor = parent.parent_page_id
        depth += 1
    return depth


def _subtree_height(pages: dict[str, WikiPageRecord], page_id: str) -> int:
    """How many levels sit BELOW `page_id` — 0 for a leaf.

    Breadth-first over the team's pages, which is cheap: the depth cap keeps a
    wiki tree small and this only runs on a move.
    """

    children: dict[str | None, list[str]] = {}
    for page in pages.values():
        children.setdefault(page.parent_page_id, []).append(page.page_id)

    height = 0
    level = children.get(page_id, [])
    seen: set[str] = {page_id}
    while level and height <= MAX_PAGE_DEPTH + 2:
        height += 1
        nxt: list[str] = []
        for node in level:
            if node in seen:
                continue
            seen.add(node)
            nxt.extend(children.get(node, []))
        level = nxt
    return height


def _is_descendant(
    pages: dict[str, WikiPageRecord], candidate_id: str, ancestor_id: str
) -> bool:
    """True when `candidate_id` sits at or under `ancestor_id` — reflexive, so
    passing a page's own id as both catches "its own parent" too. Guards a
    move that would detach a subtree from the tree by making it its own
    ancestor."""

    cursor: str | None = candidate_id
    seen: set[str] = set()
    while cursor is not None and cursor not in seen:
        if cursor == ancestor_id:
            return True
        seen.add(cursor)
        node = pages.get(cursor)
        cursor = node.parent_page_id if node else None
    return False


def _validate_new_parent(
    pages: dict[str, WikiPageRecord],
    *,
    parent_page_id: str | None,
    subtree_height: int = 0,
) -> None:
    """The parent-side checks every structural writer needs, run against a
    snapshot read inside the structural lock: the parent exists, is not the
    rules page, and the write would not land past MAX_PAGE_DEPTH.

    `subtree_height` is 0 for a plain create (one new leaf); a move passes the
    height of the subtree it carries, since the whole subtree lands under the
    new parent, not just the page being moved.
    """

    if parent_page_id is None:
        return
    parent = pages.get(parent_page_id)
    if parent is None:
        raise WikiPageNotFoundError(parent_page_id)
    if parent.kind == "rules":
        raise WikiPageRulesParentError(parent_page_id)
    if _child_depth_under(pages, parent_page_id) + subtree_height > MAX_PAGE_DEPTH:
        raise WikiPageDepthExceededError(parent_page_id)


class TeamWikiStore:
    """Storage for one platform's team wikis.

    Every method takes ``team_id`` and filters on it. That is the tenant
    boundary: one table holds every team's pages, and the caller of this store
    is responsible for having derived ``team_id`` from the authenticated
    request rather than from a path or body parameter.

    Content is append-only. ``publish_revision`` inserts a revision and moves
    the page's pointer in one conditional UPDATE, so two concurrent edits
    cannot silently overwrite one another — the loser gets
    ``WikiRevisionConflictError`` carrying what it must rebase onto.

    Every writer that can change the TREE's shape — create, move, delete, and
    proposal publication — runs inside ``_structural_lock``: a single row of a
    conditional UPDATE is not enough to keep the tree acyclic and within
    ``MAX_PAGE_DEPTH`` under concurrent writers touching different rows (two
    opposing moves, a child insert racing its parent's delete). The lock plus
    a same-transaction re-read is what makes the validation authoritative
    rather than a best-effort check against a snapshot taken before the write.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @asynccontextmanager
    async def _structural_lock(self, team_id: TeamId) -> AsyncIterator[AsyncSession]:
        """Postgres advisory lock keyed per team, held for one structural
        write's whole transaction (same primitive as
        ``TeamMetadataStore.advisory_lock``; see CONTROL-PLANE-PRODUCT-
        CONTRACT.md §49). No-op on SQLite — see the Postgres integration
        tests for the guarantee this cannot prove offline.
        """

        async with self._sessions() as s, s.begin():
            if self._engine.dialect.name == "postgresql":
                await s.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(f"team_wiki_structure:{team_id}")},
                )
            yield s

    # ---- reads ------------------------------------------------------------

    async def list_pages(
        self, team_id: TeamId, session: AsyncSession | None = None
    ) -> list[WikiPageRecord]:
        """Every page of one team, ordered for a stable tree render."""

        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TeamWikiPageRow)
                    .where(TeamWikiPageRow.team_id == str(team_id))
                    .order_by(TeamWikiPageRow.position, TeamWikiPageRow.title)
                )
            ).scalars()
            return [_to_page(row) for row in rows]

    async def get_page_by_slug(
        self, team_id: TeamId, slug: str, session: AsyncSession | None = None
    ) -> WikiPageRecord | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamWikiPageRow).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.slug == slug,
                    )
                )
            ).scalar_one_or_none()
            return _to_page(row) if row is not None else None

    async def get_page(
        self, team_id: TeamId, page_id: str, session: AsyncSession | None = None
    ) -> WikiPageRecord | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamWikiPageRow).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.page_id == page_id,
                    )
                )
            ).scalar_one_or_none()
            return _to_page(row) if row is not None else None

    async def get_revision(
        self, team_id: TeamId, revision_id: str, session: AsyncSession | None = None
    ) -> WikiRevisionRecord | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamWikiRevisionRow).where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == revision_id,
                    )
                )
            ).scalar_one_or_none()
            return _to_revision(row) if row is not None else None

    async def list_revisions(
        self,
        team_id: TeamId,
        page_id: str,
        session: AsyncSession | None = None,
        *,
        limit: int = MAX_REVISION_PAGE_SIZE,
        before: RevisionCursor | None = None,
    ) -> list[WikiRevisionRecord]:
        """Up to ``limit`` of one page's revisions, newest first, bounded in
        SQL rather than loaded whole and sliced in Python: a page edited a
        thousand times must not pull a thousand Markdown bodies out of the
        database to return 50 of them.

        ``before``, when given, is the ``(created_at, revision_id)`` of the
        oldest revision the caller already has — the same tuple the ORDER BY
        below breaks ties on, so a walk stays exact even when several
        revisions share one timestamp (an edit then a restore inside the same
        second is ordinary, see ``_utcnow``). Content included — a wiki page
        is small by construction (``MAX_PAGE_CHARS``) and the history view
        shows a diff, which needs the text anyway.
        """

        conditions = [
            TeamWikiRevisionRow.team_id == str(team_id),
            TeamWikiRevisionRow.page_id == page_id,
            # History is what happened. A proposal awaiting a human, or one
            # they refused, is not an edit of this page.
            TeamWikiRevisionRow.status.notin_(("proposed", "rejected")),
        ]
        if before is not None:
            conditions.append(
                or_(
                    TeamWikiRevisionRow.created_at < before.created_at,
                    and_(
                        TeamWikiRevisionRow.created_at == before.created_at,
                        TeamWikiRevisionRow.revision_id < before.revision_id,
                    ),
                )
            )

        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TeamWikiRevisionRow)
                    .where(*conditions)
                    # `revision_id` only breaks a tie: it is a uuid and says
                    # nothing about time, but it makes the order deterministic
                    # rather than whatever the engine returns — and it is what
                    # makes `before` an exact watermark under a tie.
                    .order_by(
                        TeamWikiRevisionRow.created_at.desc(),
                        TeamWikiRevisionRow.revision_id.desc(),
                    )
                    .limit(limit)
                )
            ).scalars()
            return [_to_revision(row) for row in rows]

    # ---- writes -----------------------------------------------------------

    async def create_page(
        self,
        *,
        team_id: TeamId,
        slug: str,
        title: str,
        content_md: str,
        author_user_id: str,
        kind: str = "page",
        parent_page_id: str | None = None,
        position: int = 0,
        author_kind: str = "human",
        agent_instance_id: str | None = None,
        session_id: str | None = None,
    ) -> WikiPageWithContent:
        """Insert a page and its first revision in one transaction.

        Parent existence, kind and depth are re-checked inside
        ``_structural_lock`` against a fresh read, not the caller's snapshot.
        """

        now = _utcnow()
        page_id = _new_id()
        revision_id = _new_id()
        try:
            async with self._structural_lock(team_id) as s:
                pages = {
                    p.page_id: p for p in await self.list_pages(team_id, session=s)
                }
                _validate_new_parent(pages, parent_page_id=parent_page_id)

                page_row = TeamWikiPageRow(
                    page_id=page_id,
                    team_id=str(team_id),
                    parent_page_id=parent_page_id,
                    slug=slug,
                    title=title,
                    kind=kind,
                    current_revision_id=revision_id,
                    needs_review=author_kind == "agent",
                    position=position,
                    created_at=now,
                    updated_at=now,
                    created_by=author_user_id,
                    updated_by=author_user_id,
                )
                revision_row = TeamWikiRevisionRow(
                    revision_id=revision_id,
                    page_id=page_id,
                    team_id=str(team_id),
                    content_md=content_md,
                    base_revision_id=None,
                    status="published",
                    author_user_id=author_user_id,
                    author_kind=author_kind,
                    agent_instance_id=agent_instance_id,
                    session_id=session_id,
                    created_at=now,
                )
                s.add(page_row)
                s.add(revision_row)
        except IntegrityError as exc:
            raise WikiPageConstraintError(slug) from exc

        return WikiPageWithContent(
            page=_to_page(page_row), revision=_to_revision(revision_row)
        )

    async def publish_revision(
        self,
        *,
        team_id: TeamId,
        page_id: str,
        content_md: str,
        base_revision_id: str | None,
        author_user_id: str,
        author_kind: str = "human",
        agent_instance_id: str | None = None,
        session_id: str | None = None,
    ) -> WikiRevisionRecord:
        """Append a revision and make it the page's current one.

        The pointer move is a CONDITIONAL update on ``current_revision_id ==
        base_revision_id``: if another write landed in between, no row matches
        and the caller is handed the current state to rebase onto rather than
        overwriting it. Doing the check as a separate SELECT would leave a
        window between reading and writing.
        """

        now = _utcnow()
        revision_id = _new_id()
        try:
            await self._publish_in_transaction(
                team_id=team_id,
                page_id=page_id,
                revision_id=revision_id,
                content_md=content_md,
                base_revision_id=base_revision_id,
                author_user_id=author_user_id,
                author_kind=author_kind,
                agent_instance_id=agent_instance_id,
                session_id=session_id,
                now=now,
            )
        except _StaleBaseWrite:
            # The transaction is rolled back, so this read sees whatever won.
            # Reading inside it would have reported the row this transaction
            # opened on — already superseded under a real interleaving, which
            # would send a rebase-and-retry client round the same loop forever.
            page = await self.get_page(team_id, page_id)
            current_id = page.current_revision_id if page else None
            current = (
                await self.get_revision(team_id, current_id) if current_id else None
            )
            raise WikiRevisionConflictError(
                current_id or "", current.content_md if current else ""
            ) from None

        return WikiRevisionRecord(
            revision_id=revision_id,
            page_id=page_id,
            team_id=team_id,
            content_md=content_md,
            base_revision_id=base_revision_id,
            author_user_id=author_user_id,
            author_kind=author_kind,
            agent_instance_id=agent_instance_id,
            session_id=session_id,
            created_at=now,
        )

    async def _publish_in_transaction(
        self,
        *,
        team_id: TeamId,
        page_id: str,
        revision_id: str,
        content_md: str,
        base_revision_id: str | None,
        author_user_id: str,
        author_kind: str,
        agent_instance_id: str | None,
        session_id: str | None,
        now: datetime,
    ) -> None:
        async with use_session(self._sessions) as s:
            page_row = (
                await s.execute(
                    select(TeamWikiPageRow).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.page_id == page_id,
                    )
                )
            ).scalar_one_or_none()
            if page_row is None:
                raise WikiPageNotFoundError(page_id)

            s.add(
                TeamWikiRevisionRow(
                    revision_id=revision_id,
                    page_id=page_id,
                    team_id=str(team_id),
                    content_md=content_md,
                    base_revision_id=base_revision_id,
                    status="published",
                    author_user_id=author_user_id,
                    author_kind=author_kind,
                    agent_instance_id=agent_instance_id,
                    session_id=session_id,
                    created_at=now,
                )
            )
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(TeamWikiPageRow)
                .where(
                    TeamWikiPageRow.team_id == str(team_id),
                    TeamWikiPageRow.page_id == page_id,
                    TeamWikiPageRow.current_revision_id == base_revision_id,
                )
                .values(
                    current_revision_id=revision_id,
                    updated_at=now,
                    updated_by=author_user_id,
                    # An agent-authored change always leaves the page marked for
                    # a human read; a human edit clears the mark, because the
                    # human editing it IS the review.
                    needs_review=author_kind == "agent",
                )
            )
            if result.rowcount == 0:
                raise _StaleBaseWrite()

            if base_revision_id:
                await s.execute(
                    update(TeamWikiRevisionRow)
                    .where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == base_revision_id,
                    )
                    .values(status="superseded")
                )

    async def update_page_metadata(
        self,
        *,
        team_id: TeamId,
        page_id: str,
        title: str | None = None,
        parent_page_id: str | None = None,
        position: int | None = None,
        clear_parent: bool = False,
        updated_by: str,
    ) -> WikiPageRecord:
        """Rename or move a page. Never touches content or the revision chain.

        A move's destination and cycle safety are re-checked inside
        ``_structural_lock`` against a fresh read; a plain rename takes the
        same lock but skips that check (see below).
        """

        values: dict[str, object] = {"updated_at": _utcnow(), "updated_by": updated_by}
        if title is not None:
            values["title"] = title
        if position is not None:
            values["position"] = position
        if clear_parent:
            values["parent_page_id"] = None
        elif parent_page_id is not None:
            values["parent_page_id"] = parent_page_id

        try:
            async with self._structural_lock(team_id) as s:
                # A plain rename or a move-to-root changes nothing about the
                # tree's shape, so it skips the team-wide read below: the
                # UPDATE's own rowcount is enough to catch a missing page, and
                # there is no parent, cycle or depth to check against.
                if not clear_parent and parent_page_id is not None:
                    pages = {
                        p.page_id: p for p in await self.list_pages(team_id, session=s)
                    }
                    if page_id not in pages:
                        raise WikiPageNotFoundError(page_id)
                    # Reflexive: this also catches a page named as its own
                    # parent, without a separate check.
                    if _is_descendant(pages, parent_page_id, page_id):
                        raise WikiPageInvalidMoveError(page_id)
                    _validate_new_parent(
                        pages,
                        parent_page_id=parent_page_id,
                        subtree_height=_subtree_height(pages, page_id),
                    )

                result: CursorResult = await s.execute(  # type: ignore[assignment]
                    update(TeamWikiPageRow)
                    .where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.page_id == page_id,
                    )
                    .values(**values)
                )
                if result.rowcount == 0:
                    raise WikiPageNotFoundError(page_id)
        except IntegrityError as exc:
            # The race the sibling-title index exists to catch: two editors
            # renaming two siblings to the same title, each passing the
            # service's check on its own snapshot. Mapped like the other write
            # paths so the loser gets a 409 rather than a 500.
            raise WikiPageConstraintError() from exc

        page = await self.get_page(team_id, page_id)
        assert page is not None
        return page

    async def set_needs_review(
        self,
        *,
        team_id: TeamId,
        page_id: str,
        needs_review: bool,
        reviewed_by: str,
        base_revision_id: str,
    ) -> WikiPageRecord:
        """Flag or clear a page's review mark, and stamp the clearing on the
        revision it applies to.

        The page-mark update is a CONDITIONAL UPDATE on `current_revision_id
        == base_revision_id`, same pattern as `publish_revision`: a
        validation only means something for the exact text the reviewer
        displayed, so a page that moved on since is refused with 409 rather
        than certifying whatever happens to be current now.

        Reviewing is not editing: `updated_at`/`updated_by` are left alone, or
        validating an agent's page would relabel it as edited by whoever read
        it. The page's own columns cannot hold the validation either — they
        would say only that the page was touched, not that this text was
        approved — so it lands on the currently published revision, where it
        stays true after the next edit moves the page on.
        """
        now = _utcnow()
        try:
            async with use_session(self._sessions) as s:
                page_row = (
                    await s.execute(
                        select(TeamWikiPageRow).where(
                            TeamWikiPageRow.team_id == str(team_id),
                            TeamWikiPageRow.page_id == page_id,
                        )
                    )
                ).scalar_one_or_none()
                if page_row is None:
                    raise WikiPageNotFoundError(page_id)

                result: CursorResult = await s.execute(  # type: ignore[assignment]
                    update(TeamWikiPageRow)
                    .where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.page_id == page_id,
                        TeamWikiPageRow.current_revision_id == base_revision_id,
                    )
                    # `updated_at` restated so the column's `onupdate` does not fire.
                    .values(
                        needs_review=needs_review,
                        updated_at=TeamWikiPageRow.updated_at,
                    )
                )
                if result.rowcount == 0:
                    raise _StaleBaseWrite()

                await s.execute(
                    update(TeamWikiRevisionRow)
                    .where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == base_revision_id,
                    )
                    # Re-flagging withdraws the validation: the text under
                    # review is the same one someone had approved.
                    .values(
                        reviewed_at=None if needs_review else now,
                        reviewed_by=None if needs_review else reviewed_by,
                    )
                )
        except _StaleBaseWrite:
            # Rolled back above; read fresh so the conflict carries whatever
            # actually won, not the row this transaction opened on.
            page = await self.get_page(team_id, page_id)
            current_id = page.current_revision_id if page else None
            current = (
                await self.get_revision(team_id, current_id) if current_id else None
            )
            raise WikiRevisionConflictError(
                current_id or "", current.content_md if current else ""
            ) from None

        page = await self.get_page(team_id, page_id)
        assert page is not None
        return page

    async def delete_page(self, *, team_id: TeamId, page_id: str) -> None:
        """Delete one leaf page and all of its revisions. Refuses one with
        children rather than cascading — the subtree loss revision history
        cannot undo. ``_structural_lock`` makes one children-check enough: no
        other writer can start while it is held, so nothing can insert a
        child in the window a stale-snapshot version needed a late re-check
        for.
        """

        async with self._structural_lock(team_id) as s:
            children = (
                await s.execute(
                    select(TeamWikiPageRow.page_id).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.parent_page_id == page_id,
                    )
                )
            ).scalars()
            if list(children):
                raise WikiPageHasChildrenError(page_id)

            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(TeamWikiPageRow).where(
                    TeamWikiPageRow.team_id == str(team_id),
                    TeamWikiPageRow.page_id == page_id,
                )
            )
            if result.rowcount == 0:
                raise WikiPageNotFoundError(page_id)
            await s.execute(
                delete(TeamWikiRevisionRow).where(
                    TeamWikiRevisionRow.team_id == str(team_id),
                    TeamWikiRevisionRow.page_id == page_id,
                )
            )

    # ---- proposals (WIKI-04) ----------------------------------------------

    async def create_proposal(
        self,
        *,
        team_id: TeamId,
        page_id: str | None,
        content_md: str,
        base_revision_id: str | None,
        proposed_title: str | None,
        proposed_parent_page_id: str | None,
        author_user_id: str,
        agent_instance_id: str | None,
        session_id: str | None,
    ) -> WikiRevisionRecord:
        """Store one `proposed` revision. Nothing about the wiki changes yet.

        `page_id` None means the proposal is for a page that does not exist:
        an id is minted here and becomes the page's own if a human approves,
        so the proposal can be diffed and published without ever putting an
        unapproved page in the team's rail.
        """

        revision = TeamWikiRevisionRow(
            revision_id=_new_id(),
            page_id=page_id or _new_id(),
            team_id=str(team_id),
            content_md=content_md,
            base_revision_id=base_revision_id,
            status="proposed",
            # The user driving the conversation, never the agent: identity here
            # is the human's, and `author_kind` is what records the origin.
            author_user_id=author_user_id,
            author_kind="agent",
            agent_instance_id=agent_instance_id,
            session_id=session_id,
            created_at=_utcnow(),
            proposed_title=proposed_title,
            proposed_parent_page_id=proposed_parent_page_id,
        )
        async with use_session(self._sessions) as s:
            s.add(revision)
        return _to_revision(revision)

    async def get_proposal(
        self, team_id: TeamId, revision_id: str, session: AsyncSession | None = None
    ) -> WikiRevisionRecord | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamWikiRevisionRow).where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == revision_id,
                        TeamWikiRevisionRow.status == "proposed",
                    )
                )
            ).scalar_one_or_none()
            return _to_revision(row) if row is not None else None

    async def publish_proposal(
        self,
        *,
        team_id: TeamId,
        revision_id: str,
        slug: str,
        approver_user_id: str,
    ) -> WikiPageRecord:
        """Turn a pending proposal into the page's current revision.

        One transaction, under ``_structural_lock`` even for a content-only
        edit: a new page's parent is re-resolved against a fresh read (gone
        means publish at the root; too deep means refuse), and an edit uses
        `publish_revision`'s own base-revision guard. `needs_review` is left
        true either way — approval means the change is wanted, not read.
        """

        now = _utcnow()
        # A slug free a moment ago can be taken between the check and this
        # insert. Surfacing the named error lets the caller answer 409 rather
        # than a bare 500 the approver can do nothing with.
        try:
            async with self._structural_lock(team_id) as s:
                row = (
                    await s.execute(
                        select(TeamWikiRevisionRow).where(
                            TeamWikiRevisionRow.team_id == str(team_id),
                            TeamWikiRevisionRow.revision_id == revision_id,
                            TeamWikiRevisionRow.status == "proposed",
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    raise WikiPageNotFoundError(revision_id)

                page_row = (
                    await s.execute(
                        select(TeamWikiPageRow).where(
                            TeamWikiPageRow.team_id == str(team_id),
                            TeamWikiPageRow.page_id == row.page_id,
                        )
                    )
                ).scalar_one_or_none()

                if page_row is None:
                    if row.proposed_title is None:
                        # An edit whose page was deleted while the proposal waited.
                        raise WikiPageNotFoundError(row.page_id)

                    pages = {
                        p.page_id: p for p in await self.list_pages(team_id, session=s)
                    }
                    parent_id = row.proposed_parent_page_id
                    if parent_id is not None and parent_id not in pages:
                        parent_id = None
                    _validate_new_parent(pages, parent_page_id=parent_id)

                    page_row = TeamWikiPageRow(
                        page_id=row.page_id,
                        team_id=str(team_id),
                        parent_page_id=parent_id,
                        slug=slug,
                        title=row.proposed_title,
                        kind="page",
                        current_revision_id=revision_id,
                        needs_review=True,
                        position=0,
                        created_at=now,
                        updated_at=now,
                        created_by=approver_user_id,
                        updated_by=approver_user_id,
                    )
                    s.add(page_row)
                    row.proposed_parent_page_id = parent_id
                else:
                    result: CursorResult = await s.execute(  # type: ignore[assignment]
                        update(TeamWikiPageRow)
                        .where(
                            TeamWikiPageRow.team_id == str(team_id),
                            TeamWikiPageRow.page_id == row.page_id,
                            TeamWikiPageRow.current_revision_id == row.base_revision_id,
                        )
                        .values(
                            current_revision_id=revision_id,
                            updated_at=now,
                            updated_by=approver_user_id,
                            needs_review=True,
                        )
                    )
                    if result.rowcount == 0:
                        raise _StaleBaseWrite()
                    if row.base_revision_id:
                        await s.execute(
                            update(TeamWikiRevisionRow)
                            .where(
                                TeamWikiRevisionRow.team_id == str(team_id),
                                TeamWikiRevisionRow.revision_id == row.base_revision_id,
                            )
                            .values(status="superseded")
                        )

                # CAS, not an ORM attribute write from the SELECT above: a
                # reject committed in between must not be overwritten back to
                # "published". See CONTROL-PLANE-PRODUCT-CONTRACT.md §49.
                approved: CursorResult = await s.execute(  # type: ignore[assignment]
                    update(TeamWikiRevisionRow)
                    .where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == revision_id,
                        TeamWikiRevisionRow.status == "proposed",
                    )
                    .values(
                        status="published",
                        # The approver is the author of record: an agent
                        # drafted it, a human decided it. Identity in this
                        # table is never the agent's.
                        author_user_id=approver_user_id,
                    )
                )
                if approved.rowcount == 0:
                    raise WikiProposalNoLongerPendingError(revision_id)
        except IntegrityError as exc:
            raise WikiPageConstraintError(slug) from exc
        refreshed = await self.get_page(team_id, row.page_id)
        if refreshed is None:  # pragma: no cover — created or updated just above
            raise WikiPageNotFoundError(row.page_id)
        return refreshed

    # ---- proposal lifecycle (WIKI-05) --------------------------------------
    # Decline and abandonment both resolve as `status="rejected"`. Full
    # rationale: CONTROL-PLANE-PRODUCT-CONTRACT.md §49.

    async def list_stale_proposals(
        self, *, older_than: datetime, limit: int
    ) -> list[StaleProposalCandidate]:
        """Every team's `proposed` rows older than `older_than`, oldest first.

        Cross-team on purpose: the lifecycle sweep is a platform service
        action, not a request scoped to one authenticated team, so this is
        the one read in this store that does not take `team_id` — callers are
        the scheduler's own lifecycle action, never the HTTP API.
        """

        async with use_session(self._sessions) as s:
            rows = (
                await s.execute(
                    select(
                        TeamWikiRevisionRow.revision_id,
                        TeamWikiRevisionRow.team_id,
                        TeamWikiRevisionRow.page_id,
                        TeamWikiRevisionRow.created_at,
                    )
                    .where(
                        TeamWikiRevisionRow.status == "proposed",
                        TeamWikiRevisionRow.created_at < older_than,
                    )
                    .order_by(TeamWikiRevisionRow.created_at)
                    .limit(limit)
                )
            ).all()
            return [
                StaleProposalCandidate(
                    revision_id=row.revision_id,
                    team_id=TeamId(row.team_id),
                    page_id=row.page_id,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def reject_stale_proposal(self, *, team_id: TeamId, revision_id: str) -> bool:
        """Flip one proposal to `rejected` — but only if it is still
        `proposed`. Returns whether it actually changed a row.

        The `WHERE status == "proposed"` guard is the whole safety story: if
        a human approved it between the sweep's list step and this UPDATE,
        this simply matches nothing and returns `False` rather than
        clobbering a page that now points at a `published` revision. No lock
        is needed — a revision's own status is not a tree-shape invariant.
        """

        async with use_session(self._sessions) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(TeamWikiRevisionRow)
                .where(
                    TeamWikiRevisionRow.team_id == str(team_id),
                    TeamWikiRevisionRow.revision_id == revision_id,
                    TeamWikiRevisionRow.status == "proposed",
                )
                .values(status="rejected")
            )
            return result.rowcount > 0

    async def reject_proposals_for_session(
        self, *, team_id: TeamId, session_id: str
    ) -> int:
        """Reject every still-`proposed` row from one session, immediately —
        used when the session is erased. A proposal whose conversation no
        longer exists is unambiguously abandoned; there is no reason to make
        it wait out the ordinary retention window. Returns the count changed.
        """

        async with use_session(self._sessions) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(TeamWikiRevisionRow)
                .where(
                    TeamWikiRevisionRow.team_id == str(team_id),
                    TeamWikiRevisionRow.session_id == session_id,
                    TeamWikiRevisionRow.status == "proposed",
                )
                .values(status="rejected")
            )
            return result.rowcount
