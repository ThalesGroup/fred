from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from control_plane_backend.models.team_wiki_models import (
    MAX_PAGE_CHARS,
    MAX_RULES_CHARS,
)


class WikiPageSummary(BaseModel):
    """One node of the page tree — everything the sidebar needs, no content."""

    page_id: str
    slug: str
    title: str
    kind: str = Field(description='"page", or "rules" for the reserved rules page.')
    parent_page_id: str | None = None
    # Bounded: the column is a 32-bit int, and an out-of-range value should be a
    # 422 from the schema rather than an integrity error surfacing as a 500.
    position: int = Field(default=0, ge=0, le=1_000_000)
    needs_review: bool = Field(
        default=False,
        description=(
            "An agent wrote the current revision and no editor has cleared the "
            "mark yet. This is the editors' review queue."
        ),
    )
    updated_at: datetime | None = None
    updated_by: str | None = None


class WikiPageTree(BaseModel):
    """Every page of one team's wiki, flat. The client assembles the tree from
    `parent_page_id` — the depth cap makes that cheap, and a flat payload keeps
    the response shape stable if nesting rules ever change."""

    pages: list[WikiPageSummary] = Field(default_factory=list)


class WikiRevisionSummary(BaseModel):
    """One entry of a page's history."""

    revision_id: str
    status: str
    author_user_id: str
    author_kind: str = Field(description='"human" or "agent".')
    agent_instance_id: str | None = None
    session_id: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = Field(
        default=None,
        description=(
            "When an editor cleared the review mark while this revision was "
            "published. The history shows it as its own entry: the person who "
            "validates an agent's text is not always the one it was written for."
        ),
    )
    reviewed_by: str | None = None


class WikiPageDetail(BaseModel):
    """One page and the content currently published on it."""

    page: WikiPageSummary
    content_md: str = ""
    revision_id: str | None = None
    author_kind: str = "human"


class WikiRevisionList(BaseModel):
    revisions: list[WikiRevisionSummary] = Field(default_factory=list)
    contents: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Revision id to its Markdown, so the history view can diff without "
            "one request per revision. Pages are capped at "
            f"{MAX_PAGE_CHARS} characters, which bounds this."
        ),
    )


class CreateWikiPageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content_md: str = Field(default="", max_length=MAX_PAGE_CHARS)
    parent_page_id: str | None = None
    # Bounded like its siblings above: the column is a 32-bit int, and an
    # out-of-range value belongs in a 422 from the schema rather than a
    # DataError surfacing as a 500.
    position: int = Field(default=0, ge=0, le=1_000_000)


class UpdateWikiPageContentRequest(BaseModel):
    content_md: str = Field(max_length=MAX_PAGE_CHARS)
    base_revision_id: str | None = Field(
        default=None,
        description=(
            "The revision the author started from — read it from the page "
            "first. The write is refused with 409 if the page has moved on "
            "since, so the last writer cannot silently erase the one before. "
            "Omitting it on a page that already has a revision is refused the "
            "same way: there is no unconditional overwrite."
        ),
    )


class UpdateWikiPageMetadataRequest(BaseModel):
    """Rename or move. Content is untouched — that is a separate call, so a
    rename never appears in the page's revision history."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    parent_page_id: str | None = None
    move_to_root: bool = False
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class UpdateWikiRulesRequest(BaseModel):
    content_md: str = Field(max_length=MAX_RULES_CHARS)
    base_revision_id: str | None = None


class SetNeedsReviewRequest(BaseModel):
    needs_review: bool


class WikiConflictResponse(BaseModel):
    """Returned with 409 when a write's base revision is stale."""

    detail: str
    current_revision_id: str
    current_content_md: str


class WikiAvailability(BaseModel):
    """Whether this team has a wiki at all.

    A team has one when an admin has enabled the `team_wiki` agent capability
    for it. Its own endpoint so the navigation panel can decide whether to
    offer the wiki without fetching the page tree to find out.
    """

    enabled: bool


# --- Agent proposals (WIKI-04) ---------------------------------------------


class ProposePageRequest(BaseModel):
    """An agent's suggestion for a page that does not exist yet."""

    title: str = Field(min_length=1, max_length=300)
    content_md: str = Field(max_length=MAX_PAGE_CHARS)
    parent_slug: str | None = None
    agent_instance_id: str | None = None
    session_id: str | None = None


class ProposeEditRequest(BaseModel):
    """An agent's suggestion for an existing page, by slug."""

    slug: str = Field(min_length=1)
    content_md: str = Field(max_length=MAX_PAGE_CHARS)
    base_revision_id: str = Field(
        min_length=1,
        description=(
            "The revision_id a prior read of this page returned. Refused "
            "with 409 when it no longer matches the page's current revision "
            "— read the page again and redo the edit against the current "
            "text. There is no unconditional proposal: a stale or fabricated "
            "base is refused rather than silently rebased onto whatever is "
            "current."
        ),
    )
    agent_instance_id: str | None = None
    session_id: str | None = None


class WikiProposal(BaseModel):
    """A pending suggestion, and everything the approval modal needs to show
    what it would change — including the text it would replace."""

    proposal_id: str
    kind: Literal["page", "edit"]
    title: str
    slug: str | None = None
    parent_slug: str | None = None
    content_md: str
    #: What the page holds today; empty for a proposed new page.
    current_content_md: str = ""
    created_at: datetime | None = None
    author_user_id: str = ""
    agent_instance_id: str | None = None
