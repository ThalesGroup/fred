from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

#: Slug of the one page per team whose content is injected into the system
#: prompt of every agent holding the wiki capability. A fixed slug is what makes
#: it unique per team: the ``(team_id, slug)`` constraint below already forbids a
#: second one, so no partial index is needed.
RULES_PAGE_SLUG = "__rules__"

#: Longest a page may be. Pages are read whole by agents and rendered whole in
#: the UI; past this it is a document, and documents belong in the corpus.
MAX_PAGE_CHARS = 100_000

#: Longest the rules page may be. It rides on EVERY turn of every agent holding
#: the capability, on top of a baseline system prompt already near 16.7k tokens.
MAX_RULES_CHARS = 4_000

#: Deepest a page may sit. The root is depth 0.
MAX_PAGE_DEPTH = 3


class TeamWikiPageRow(Base):
    """ORM model for the ``team_wiki_pages`` table.

    One page of one team's wiki: its identity, its place in the tree, and a
    pointer to the revision currently published. The content itself lives in
    ``team_wiki_revisions`` and is never modified in place.

    One table holds every team's pages, so ``team_id`` IS the tenant boundary:
    it is always derived server-side from the authenticated request, never read
    from a caller-supplied parameter. A table per team was rejected because it
    would mean DDL on team creation, outside Alembic — see the RFC §5.3.
    """

    __tablename__ = "team_wiki_pages"
    __table_args__ = (
        UniqueConstraint("team_id", "slug", name="uq_team_wiki_pages_team_slug"),
    )

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Plain column, not a foreign key — same rationale as every other
    # control-plane table: install/uninstall and delete ordering stay free.
    # NULL at the root of the tree.
    parent_page_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # "page" or "rules". The rules page is an ordinary page with a reserved slug
    # so it inherits history, attribution and restore for free; `kind` is what
    # the agent write path filters on, which keeps that exclusion one explicit
    # test rather than a slug comparison scattered across call sites.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="page")
    # NULL only in the instant between inserting a page and its first revision.
    current_revision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when an agent-authored revision is published, cleared by an editor.
    # This is what gives editors a review queue without building one.
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)


class TeamWikiRevisionRow(Base):
    """ORM model for the ``team_wiki_revisions`` table.

    Append-only. An edit never updates a row here: it inserts a new one and
    moves the page's ``current_revision_id``. History, restore and conflict
    detection are consequences of that shape rather than features built on top.

    ``base_revision_id`` is what the author started from. A write whose base no
    longer matches the page's current revision is refused, so the last writer
    cannot silently erase the one before.
    """

    __tablename__ = "team_wiki_revisions"

    revision_id: Mapped[str] = mapped_column(String, primary_key=True)
    page_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Denormalised from the page so every read filters on the tenant boundary
    # without a join — and so a revision can never be reached through a page of
    # another team by an id mix-up.
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    base_revision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # "published", "proposed", "rejected" or "superseded". Slice 1 writes only
    # "published" and "superseded"; the agent write path (slice 4) is what makes
    # a revision sit in "proposed" while a human decides.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    # Always a real user: the human who wrote the page, or the one who approved
    # an agent's proposal. Identity is never the agent's.
    author_user_id: Mapped[str] = mapped_column(String, nullable=False)
    # "human" or "agent" — declared by the writer, not cryptographically proven
    # (RFC §10 residual 2). Drives the review mark and the page's origin badge.
    author_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="human"
    )
    agent_instance_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # The conversation an agent revision came from — the audit trail back to the
    # context that produced it.
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
