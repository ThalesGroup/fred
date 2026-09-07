from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.team_wiki_models import (
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


class WikiPageHasChildrenError(Exception):
    """Refusing to delete a page that still has children."""


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
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

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
        self, team_id: TeamId, page_id: str, session: AsyncSession | None = None
    ) -> list[WikiRevisionRecord]:
        """One page's revisions, newest first. Content included — a wiki page is
        small by construction (``MAX_PAGE_CHARS``) and the history view shows a
        diff, which needs the text anyway."""

        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TeamWikiRevisionRow)
                    .where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.page_id == page_id,
                        # History is what happened. A proposal awaiting a human,
                        # or one they refused, is not an edit of this page.
                        TeamWikiRevisionRow.status.notin_(("proposed", "rejected")),
                    )
                    # `revision_id` only breaks a tie: it is a uuid and says
                    # nothing about time, but it makes the order deterministic
                    # rather than whatever the engine returns.
                    .order_by(
                        TeamWikiRevisionRow.created_at.desc(),
                        TeamWikiRevisionRow.revision_id.desc(),
                    )
                )
            ).scalars()
            return [_to_revision(row) for row in rows]

    async def count_children(
        self, team_id: TeamId, page_id: str, session: AsyncSession | None = None
    ) -> int:
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(TeamWikiPageRow.page_id).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.parent_page_id == page_id,
                    )
                )
            ).scalars()
            return len(list(rows))

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
        """Insert a page and its first revision in one transaction."""

        now = _utcnow()
        page_id = _new_id()
        revision_id = _new_id()
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
        try:
            async with use_session(self._sessions) as s:
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
        """Rename or move a page. Never touches content or the revision chain."""

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
            async with use_session(self._sessions) as s:
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
        self, *, team_id: TeamId, page_id: str, needs_review: bool, reviewed_by: str
    ) -> WikiPageRecord:
        """Flag or clear a page's review mark, and stamp the clearing on the
        revision it applies to.

        Reviewing is not editing: `updated_at`/`updated_by` are left alone, or
        validating an agent's page would relabel it as edited by whoever read
        it. The page's own columns cannot hold the validation either — they
        would say only that the page was touched, not that this text was
        approved — so it lands on the currently published revision, where it
        stays true after the next edit moves the page on.
        """
        now = _utcnow()
        async with use_session(self._sessions) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(TeamWikiPageRow)
                .where(
                    TeamWikiPageRow.team_id == str(team_id),
                    TeamWikiPageRow.page_id == page_id,
                )
                # `updated_at` restated so the column's `onupdate` does not fire.
                .values(
                    needs_review=needs_review,
                    updated_at=TeamWikiPageRow.updated_at,
                )
            )
            if result.rowcount == 0:
                raise WikiPageNotFoundError(page_id)

            current_revision_id = await s.scalar(
                select(TeamWikiPageRow.current_revision_id).where(
                    TeamWikiPageRow.team_id == str(team_id),
                    TeamWikiPageRow.page_id == page_id,
                )
            )
            if current_revision_id:
                await s.execute(
                    update(TeamWikiRevisionRow)
                    .where(
                        TeamWikiRevisionRow.team_id == str(team_id),
                        TeamWikiRevisionRow.revision_id == current_revision_id,
                    )
                    # Re-flagging withdraws the validation: the text under
                    # review is the same one someone had approved.
                    .values(
                        reviewed_at=None if needs_review else now,
                        reviewed_by=None if needs_review else reviewed_by,
                    )
                )

        page = await self.get_page(team_id, page_id)
        assert page is not None
        return page

    async def delete_page(self, *, team_id: TeamId, page_id: str) -> None:
        """Delete one leaf page and all of its revisions.

        Refuses a page that still has children rather than cascading: an
        accidental subtree deletion is the one thing revision history cannot
        undo, since the pages themselves are gone.
        """

        async with use_session(self._sessions) as s:
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
            # Re-check inside the same transaction: a child committed between
            # the check above and this delete would be left pointing at a page
            # that no longer exists — unreachable from the tree but still
            # holding its slug, which is the outcome the guard exists to
            # prevent. Raising here rolls the whole delete back.
            late_children = (
                await s.execute(
                    select(TeamWikiPageRow.page_id).where(
                        TeamWikiPageRow.team_id == str(team_id),
                        TeamWikiPageRow.parent_page_id == page_id,
                    )
                )
            ).scalars()
            if list(late_children):
                raise WikiPageHasChildrenError(page_id)

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

    async def reparent_proposal(
        self, *, team_id: TeamId, revision_id: str, parent_page_id: str | None
    ) -> None:
        """Re-point a pending proposal's parent, when the one it named is gone.

        The only field of a proposal that may change before approval, and only
        towards the root: a proposal is approved or refused as a whole
        (RFC §8.2), never edited into something else.
        """

        async with use_session(self._sessions) as s:
            await s.execute(
                update(TeamWikiRevisionRow)
                .where(
                    TeamWikiRevisionRow.team_id == str(team_id),
                    TeamWikiRevisionRow.revision_id == revision_id,
                    TeamWikiRevisionRow.status == "proposed",
                )
                .values(proposed_parent_page_id=parent_page_id)
            )

    async def publish_proposal(
        self,
        *,
        team_id: TeamId,
        revision_id: str,
        slug: str,
        approver_user_id: str,
    ) -> WikiPageRecord:
        """Turn a pending proposal into the page's current revision.

        One transaction: for a new page it creates the page row and points it
        at the proposal; for an edit it moves `current_revision_id` under the
        same base-revision guard `publish_revision` uses, so a proposal written
        against text someone has since changed is refused rather than silently
        overwriting them.

        The page is left `needs_review=True` either way — the approval says the
        change is wanted, not that the page has been read as a whole.
        """

        now = _utcnow()
        # A slug free a moment ago can be taken between the check and this
        # insert. Surfacing the named error lets the caller answer 409 rather
        # than a bare 500 the approver can do nothing with.
        try:
            async with use_session(self._sessions) as s:
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
                    page_row = TeamWikiPageRow(
                        page_id=row.page_id,
                        team_id=str(team_id),
                        parent_page_id=row.proposed_parent_page_id,
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

                row.status = "published"
                # The approver is the author of record: an agent drafted it, a human
                # decided it. Identity in this table is never the agent's.
                row.author_user_id = approver_user_id
        except IntegrityError as exc:
            raise WikiPageConstraintError(slug) from exc
        refreshed = await self.get_page(team_id, row.page_id)
        if refreshed is None:  # pragma: no cover — created or updated just above
            raise WikiPageNotFoundError(row.page_id)
        return refreshed
