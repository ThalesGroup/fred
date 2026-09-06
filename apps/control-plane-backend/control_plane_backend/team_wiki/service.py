from __future__ import annotations

import re
import unicodedata

from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.security.rebac.rebac_engine import TeamPermission

from control_plane_backend.models.team_wiki_models import (
    MAX_PAGE_DEPTH,
    RULES_PAGE_SLUG,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.team_wiki.schemas import (
    ProposeEditRequest,
    ProposePageRequest,
    WikiAvailability,
    WikiProposal,
    CreateWikiPageRequest,
    SetNeedsReviewRequest,
    UpdateWikiPageContentRequest,
    UpdateWikiPageMetadataRequest,
    UpdateWikiRulesRequest,
    WikiPageDetail,
    WikiPageSummary,
    WikiPageTree,
    WikiRevisionList,
    WikiRevisionSummary,
)
from control_plane_backend.team_wiki.store import (
    TeamWikiStore,
    WikiRevisionRecord,
    _StaleBaseWrite,
    WikiPageHasChildrenError,
    WikiPageNotFoundError,
    WikiPageRecord,
    WikiRevisionConflictError,
    WikiSlugAlreadyExistsError,
)
from control_plane_backend.capabilities.authz import can_team_use_capability
from control_plane_backend.teams.service import require_team_access

# Read is member-only, NOT `CAN_READ`: `can_read` is `team_member or public`, so
# on a team flagged public it would hand the wiki to non-members — and a wiki
# holds a team's internal knowledge. `CAN_READ_MEMEBERS` is the codebase's
# existing idiom for "member-only read of a team's internals"; the routing
# policy read gate uses it the same way.
WIKI_READ_PERMISSION = TeamPermission.CAN_READ_MEMEBERS

# Write is `team_editor`, exactly as for the team's other content.
# `team_admin` has no write authority here — the roles are orthogonal, not
# hierarchical (`platform/REBAC.md`). A personal-space owner holds
# `team_editor` on their own space, so this is one code path for both.
WIKI_WRITE_PERMISSION = TeamPermission.CAN_UPDATE_RESOURCES

#: The agent capability whose enablement makes a team's wiki exist at all.
#: An admin turning it off takes the wiki away from the team's agents AND its
#: people — the two are one decision on purpose: a wiki nothing can read into a
#: conversation is a document store, which the team space already is. Turning it
#: off never deletes anything; the tables are untouched and re-enabling brings
#: the wiki back exactly as it was.
TEAM_WIKI_CAPABILITY_ID = "team_wiki"

#: Most revisions one history response returns, newest first.
MAX_REVISIONS_RETURNED = 50


async def _require_wiki_access(
    user: KeycloakUser,
    team_id: TeamId,
    deps: ProductServiceDependencies,
    permissions: list[TeamPermission],
) -> TeamId:
    """Resolve the caller's access to this team's wiki, or refuse.

    Two gates, in this order: the team membership/role one every wiki route
    already had, then the capability one. Both live here rather than in each
    entry point so a route added later cannot forget either — the whole
    service reaches its store through this function.

    404, not 403, when the capability is off: to a team without it, this team
    has no wiki, and that is the same answer a nonexistent team gets. The
    anti-guessing rule the rest of the codebase applies to hidden templates.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, permissions
    )
    if not await can_team_use_capability(
        deps.team_dependencies.rebac,
        team_id,
        capability_id=TEAM_WIKI_CAPABILITY_ID,
    ):
        raise WikiRequestError("This team has no wiki.", http_status=404)
    return team_id


class WikiRequestError(Exception):
    """A wiki operation the caller cannot perform, with the status to return."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


class WikiConflictError(Exception):
    """A write whose base revision is stale, carrying what to rebase onto."""

    def __init__(self, current_revision_id: str, current_content_md: str) -> None:
        super().__init__("This page has changed since your edit was prepared.")
        self.current_revision_id = current_revision_id
        self.current_content_md = current_content_md


def slugify(title: str) -> str:
    """A URL- and tool-friendly slug for a page title.

    Accents are folded rather than dropped so a French title keeps its words:
    "Décisions d'équipe" becomes "decisions-d-equipe", not "d-quipe".
    """

    folded = unicodedata.normalize("NFKD", title)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:150] or "page"


async def _unique_slug(store: TeamWikiStore, team_id: TeamId, title: str) -> str:
    """`slugify(title)`, suffixed until it is free in this team."""

    base = slugify(title)
    taken = {page.slug for page in await store.list_pages(team_id)}
    if base not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base}-{n}"
        if candidate not in taken:
            return candidate
    raise WikiRequestError("Too many pages with a similar title.", http_status=409)


def _summary(page: WikiPageRecord) -> WikiPageSummary:
    return WikiPageSummary(
        page_id=page.page_id,
        slug=page.slug,
        title=page.title,
        kind=page.kind,
        parent_page_id=page.parent_page_id,
        position=page.position,
        needs_review=page.needs_review,
        updated_at=page.updated_at,
        updated_by=page.updated_by,
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
    """True when `candidate_id` sits under `ancestor_id`. Guards a move that
    would detach a subtree from the tree by making it its own parent."""

    cursor: str | None = candidate_id
    seen: set[str] = set()
    while cursor is not None and cursor not in seen:
        if cursor == ancestor_id:
            return True
        seen.add(cursor)
        node = pages.get(cursor)
        cursor = node.parent_page_id if node else None
    return False


async def _require_page(
    store: TeamWikiStore, team_id: TeamId, page_id: str
) -> WikiPageRecord:
    page = await store.get_page(team_id, page_id)
    if page is None:
        raise WikiRequestError("This wiki page does not exist.", http_status=404)
    return page


async def _detail(
    store: TeamWikiStore, team_id: TeamId, page: WikiPageRecord
) -> WikiPageDetail:
    revision = (
        await store.get_revision(team_id, page.current_revision_id)
        if page.current_revision_id
        else None
    )
    return WikiPageDetail(
        page=_summary(page),
        content_md=revision.content_md if revision else "",
        revision_id=revision.revision_id if revision else None,
        author_kind=revision.author_kind if revision else "human",
    )


# ---- reads ----------------------------------------------------------------


async def get_wiki_availability(
    user: KeycloakUser, team_id: TeamId, deps: ProductServiceDependencies
) -> WikiAvailability:
    """Does this team have a wiki?

    Deliberately NOT behind `_require_wiki_access`: the whole point is to
    answer "no" for a team whose capability is off, which that helper turns
    into a 404. Team membership is still required — whether a team runs a wiki
    is its own business.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [WIKI_READ_PERMISSION]
    )
    enabled = await can_team_use_capability(
        deps.team_dependencies.rebac,
        team_id,
        capability_id=TEAM_WIKI_CAPABILITY_ID,
    )
    return WikiAvailability(enabled=enabled)


async def get_wiki_tree(
    user: KeycloakUser, team_id: TeamId, deps: ProductServiceDependencies
) -> WikiPageTree:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    pages = await store.list_pages(team_id)
    return WikiPageTree(pages=[_summary(p) for p in pages])


async def get_wiki_page(
    user: KeycloakUser, team_id: TeamId, slug: str, deps: ProductServiceDependencies
) -> WikiPageDetail:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await store.get_page_by_slug(team_id, slug)
    if page is None:
        raise WikiRequestError("This wiki page does not exist.", http_status=404)
    return await _detail(store, team_id, page)


async def list_wiki_revisions(
    user: KeycloakUser, team_id: TeamId, page_id: str, deps: ProductServiceDependencies
) -> WikiRevisionList:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    await _require_page(store, team_id, page_id)
    # Bounded: one revision is capped, their NUMBER is not, so a page edited a
    # thousand times would otherwise return a thousand full documents at once.
    # Newest first, so the cut falls on the oldest history.
    revisions = (await store.list_revisions(team_id, page_id))[:MAX_REVISIONS_RETURNED]
    return WikiRevisionList(
        revisions=[
            WikiRevisionSummary(
                revision_id=r.revision_id,
                status=r.status,
                author_user_id=r.author_user_id,
                author_kind=r.author_kind,
                agent_instance_id=r.agent_instance_id,
                session_id=r.session_id,
                created_at=r.created_at,
            )
            for r in revisions
        ],
        contents={r.revision_id: r.content_md for r in revisions},
    )


async def get_wiki_rules(
    user: KeycloakUser, team_id: TeamId, deps: ProductServiceDependencies
) -> WikiPageDetail:
    """The rules page, or an empty stand-in when the team has never written one.

    This is a READ, gated on the member-only read permission, so it must not
    write. Materialising the row here would let any team member create the page
    that steers every agent's system prompt, and be recorded as its author. The
    row appears on the first PUT, which is editor-only.
    """

    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await store.get_page_by_slug(team_id, RULES_PAGE_SLUG)
    if page is not None:
        return await _detail(store, team_id, page)

    return WikiPageDetail(
        page=WikiPageSummary(
            page_id="", slug=RULES_PAGE_SLUG, title="Rules", kind="rules"
        ),
        content_md="",
        revision_id=None,
    )


# ---- writes ---------------------------------------------------------------


async def create_wiki_page(
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateWikiPageRequest,
    deps: ProductServiceDependencies,
) -> WikiPageDetail:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()

    if request.parent_page_id is not None:
        pages = {p.page_id: p for p in await store.list_pages(team_id)}
        parent = pages.get(request.parent_page_id)
        if parent is None:
            raise WikiRequestError("The parent page does not exist.", http_status=404)
        if parent.kind == "rules":
            raise WikiRequestError(
                "The rules page cannot have children.", http_status=400
            )
        if _child_depth_under(pages, request.parent_page_id) > MAX_PAGE_DEPTH:
            raise WikiRequestError(
                f"A wiki page cannot sit deeper than {MAX_PAGE_DEPTH} levels.",
                http_status=400,
            )

    slug = await _unique_slug(store, team_id, request.title)
    try:
        created = await store.create_page(
            team_id=team_id,
            slug=slug,
            title=request.title,
            content_md=request.content_md,
            parent_page_id=request.parent_page_id,
            position=request.position,
            author_user_id=user.uid,
        )
    except WikiSlugAlreadyExistsError as exc:
        raise WikiRequestError(
            "A page with this title already exists.", http_status=409
        ) from exc
    return WikiPageDetail(
        page=_summary(created.page),
        content_md=request.content_md,
        revision_id=created.revision.revision_id if created.revision else None,
    )


async def update_wiki_page_content(
    user: KeycloakUser,
    team_id: TeamId,
    page_id: str,
    request: UpdateWikiPageContentRequest,
    deps: ProductServiceDependencies,
) -> WikiPageDetail:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await _require_page(store, team_id, page_id)
    if page.kind == "rules":
        raise WikiRequestError(
            "The rules page is edited through its own endpoint.", http_status=400
        )
    return await _publish(
        store,
        team_id=team_id,
        page=page,
        content_md=request.content_md,
        base_revision_id=request.base_revision_id,
        author_user_id=user.uid,
    )


async def update_wiki_rules(
    user: KeycloakUser,
    team_id: TeamId,
    request: UpdateWikiRulesRequest,
    deps: ProductServiceDependencies,
) -> WikiPageDetail:
    """Edit the rules page. Editors only, and never reachable by an agent —
    the agent write path has no tool that targets a `kind="rules"` page."""

    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await store.get_page_by_slug(team_id, RULES_PAGE_SLUG)
    if page is None:
        try:
            created = await store.create_page(
                team_id=team_id,
                slug=RULES_PAGE_SLUG,
                title="Rules",
                content_md=request.content_md,
                kind="rules",
                author_user_id=user.uid,
            )
        except WikiSlugAlreadyExistsError:
            # Two editors saved the rules page for the first time at once. The
            # loser re-reads and takes the ordinary conflict path rather than
            # surfacing an integrity error as a 500.
            page = await store.get_page_by_slug(team_id, RULES_PAGE_SLUG)
            if page is None:
                raise
        else:
            return WikiPageDetail(
                page=_summary(created.page),
                content_md=request.content_md,
                revision_id=created.revision.revision_id if created.revision else None,
            )
    # No fallback to the page's own current revision: omitting `base_revision_id`
    # on a page that already has one is REFUSED, not read as consent to
    # overwrite. The caller reads, then writes back what it read.
    return await _publish(
        store,
        team_id=team_id,
        page=page,
        content_md=request.content_md,
        base_revision_id=request.base_revision_id,
        author_user_id=user.uid,
    )


async def _publish(
    store: TeamWikiStore,
    *,
    team_id: TeamId,
    page: WikiPageRecord,
    content_md: str,
    base_revision_id: str | None,
    author_user_id: str,
) -> WikiPageDetail:
    try:
        revision = await store.publish_revision(
            team_id=team_id,
            page_id=page.page_id,
            content_md=content_md,
            base_revision_id=base_revision_id,
            author_user_id=author_user_id,
        )
    except WikiRevisionConflictError as exc:
        raise WikiConflictError(
            exc.current_revision_id, exc.current_content_md
        ) from exc
    except WikiPageNotFoundError as exc:
        raise WikiRequestError(
            "This wiki page does not exist.", http_status=404
        ) from exc

    refreshed = await store.get_page(team_id, page.page_id)
    return WikiPageDetail(
        page=_summary(refreshed or page),
        content_md=revision.content_md,
        revision_id=revision.revision_id,
        author_kind=revision.author_kind,
    )


async def update_wiki_page_metadata(
    user: KeycloakUser,
    team_id: TeamId,
    page_id: str,
    request: UpdateWikiPageMetadataRequest,
    deps: ProductServiceDependencies,
) -> WikiPageSummary:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    pages = {p.page_id: p for p in await store.list_pages(team_id)}
    page = pages.get(page_id)
    if page is None:
        raise WikiRequestError("This wiki page does not exist.", http_status=404)
    if page.kind == "rules":
        raise WikiRequestError(
            "The rules page cannot be renamed or moved.", http_status=400
        )

    if request.parent_page_id is not None and not request.move_to_root:
        if request.parent_page_id == page_id:
            raise WikiRequestError("A page cannot be its own parent.", http_status=400)
        parent = pages.get(request.parent_page_id)
        if parent is None:
            raise WikiRequestError("The parent page does not exist.", http_status=404)
        if parent.kind == "rules":
            raise WikiRequestError(
                "The rules page cannot have children.", http_status=400
            )
        # Moving a page under its own descendant would cut that whole subtree
        # off the tree — it would still exist in the table and be unreachable
        # from the root, which reads as data loss.
        if _is_descendant(pages, request.parent_page_id, page_id):
            raise WikiRequestError(
                "A page cannot be moved under one of its own children.",
                http_status=400,
            )
        # The destination's depth is not enough: a move carries the whole
        # subtree with it, so a shallow-looking move can push a grandchild past
        # the cap. Without this, create-then-move defeats it entirely.
        new_depth = _child_depth_under(pages, request.parent_page_id)
        if new_depth + _subtree_height(pages, page_id) > MAX_PAGE_DEPTH:
            raise WikiRequestError(
                f"A wiki page cannot sit deeper than {MAX_PAGE_DEPTH} levels.",
                http_status=400,
            )

    updated = await store.update_page_metadata(
        team_id=team_id,
        page_id=page_id,
        title=request.title,
        parent_page_id=request.parent_page_id,
        position=request.position,
        clear_parent=request.move_to_root,
        updated_by=user.uid,
    )
    return _summary(updated)


async def restore_wiki_revision(
    user: KeycloakUser,
    team_id: TeamId,
    page_id: str,
    revision_id: str,
    deps: ProductServiceDependencies,
) -> WikiPageDetail:
    """Restore an earlier revision by publishing its content as a NEW revision.

    History is never rewritten: what was there stays readable, and the restore
    is itself an entry in the page's history.
    """

    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await _require_page(store, team_id, page_id)
    revision = await store.get_revision(team_id, revision_id)
    if revision is None or revision.page_id != page_id:
        raise WikiRequestError(
            "This revision does not belong to this page.", http_status=404
        )
    if revision.status in ("proposed", "rejected"):
        # A proposal is not history. Restoring one would publish an agent's
        # draft as a human edit — clearing the review mark in the process —
        # which is exactly the decision the approval gate exists to record.
        raise WikiRequestError("This revision was never published.", http_status=404)
    return await _publish(
        store,
        team_id=team_id,
        page=page,
        content_md=revision.content_md,
        base_revision_id=page.current_revision_id,
        author_user_id=user.uid,
    )


async def set_wiki_page_needs_review(
    user: KeycloakUser,
    team_id: TeamId,
    page_id: str,
    request: SetNeedsReviewRequest,
    deps: ProductServiceDependencies,
) -> WikiPageSummary:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    await _require_page(store, team_id, page_id)
    updated = await store.set_needs_review(
        team_id=team_id,
        page_id=page_id,
        needs_review=request.needs_review,
        updated_by=user.uid,
    )
    return _summary(updated)


async def delete_wiki_page(
    user: KeycloakUser, team_id: TeamId, page_id: str, deps: ProductServiceDependencies
) -> None:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_WRITE_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await _require_page(store, team_id, page_id)
    if page.kind == "rules":
        raise WikiRequestError("The rules page cannot be deleted.", http_status=400)
    try:
        await store.delete_page(team_id=team_id, page_id=page_id)
    except WikiPageHasChildrenError as exc:
        raise WikiRequestError(
            "Delete or move this page's children first.", http_status=409
        ) from exc
    except WikiPageNotFoundError as exc:
        raise WikiRequestError(
            "This wiki page does not exist.", http_status=404
        ) from exc


# ---------------------------------------------------------------------------
# Agent proposals (WIKI-04)
#
# The write half is deliberately two steps. The platform's HITL gate pauses a
# tool BEFORE it runs and carries only a truncated argument preview, which
# cannot hold a page. So an agent first stores a proposal — invisible in the
# wiki, changing nothing — and then asks to publish it; that second call is
# what a human approves, and the approval modal fetches the proposal by id to
# show the diff.
#
# Proposing is member-level, not editor: §9 of the RFC opens contribution to
# any member driving an agent, and the approval gate plus the review mark are
# what make that defensible. Nothing an agent proposes reaches the wiki
# without a person saying so.
# ---------------------------------------------------------------------------


def _proposal_view(
    proposal: WikiRevisionRecord,
    *,
    page: WikiPageRecord | None,
    current_content_md: str,
    parent_slug: str | None,
) -> WikiProposal:
    return WikiProposal(
        proposal_id=proposal.revision_id,
        # From the proposal itself, never from whether the page still resolves:
        # an edit whose page was deleted while it waited is a broken edit, and
        # rendering it as a brand-new page would show the approver a diff of the
        # whole body against nothing.
        kind="page" if proposal.proposed_title is not None else "edit",
        title=page.title if page is not None else (proposal.proposed_title or ""),
        slug=page.slug if page is not None else None,
        parent_slug=parent_slug,
        content_md=proposal.content_md,
        current_content_md=current_content_md,
        created_at=proposal.created_at,
        author_user_id=proposal.author_user_id,
        agent_instance_id=proposal.agent_instance_id,
    )


async def propose_wiki_page(
    user: KeycloakUser,
    team_id: TeamId,
    request: ProposePageRequest,
    deps: ProductServiceDependencies,
) -> WikiProposal:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    pages = {p.page_id: p for p in await store.list_pages(team_id)}

    parent: WikiPageRecord | None = None
    if request.parent_slug:
        parent = next(
            (p for p in pages.values() if p.slug == request.parent_slug), None
        )
        if parent is None:
            raise WikiRequestError(
                f"No wiki page has the slug {request.parent_slug!r}.", http_status=404
            )
        if parent.kind == "rules":
            raise WikiRequestError(
                "The rules page cannot have children.", http_status=400
            )
        if _child_depth_under(pages, parent.page_id) > MAX_PAGE_DEPTH:
            raise WikiRequestError(
                f"A wiki page cannot sit deeper than {MAX_PAGE_DEPTH} levels.",
                http_status=400,
            )

    proposal = await store.create_proposal(
        team_id=team_id,
        page_id=None,
        content_md=request.content_md,
        base_revision_id=None,
        proposed_title=request.title,
        proposed_parent_page_id=parent.page_id if parent else None,
        author_user_id=user.uid,
        agent_instance_id=request.agent_instance_id,
        session_id=request.session_id,
    )
    return _proposal_view(
        proposal,
        page=None,
        current_content_md="",
        parent_slug=parent.slug if parent else None,
    )


async def propose_wiki_edit(
    user: KeycloakUser,
    team_id: TeamId,
    request: ProposeEditRequest,
    deps: ProductServiceDependencies,
) -> WikiProposal:
    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    page = await store.get_page_by_slug(team_id, request.slug)
    if page is None:
        raise WikiRequestError("This wiki page does not exist.", http_status=404)
    if page.kind == "rules":
        # §8.6: no agent can touch the rules page under any configuration. This
        # is the only place that could have been the exception, so it is not.
        raise WikiRequestError(
            "The rules page cannot be changed by an agent.", http_status=403
        )

    current = (
        await store.get_revision(team_id, page.current_revision_id)
        if page.current_revision_id
        else None
    )
    proposal = await store.create_proposal(
        team_id=team_id,
        page_id=page.page_id,
        content_md=request.content_md,
        base_revision_id=page.current_revision_id,
        proposed_title=None,
        proposed_parent_page_id=None,
        author_user_id=user.uid,
        agent_instance_id=request.agent_instance_id,
        session_id=request.session_id,
    )
    return _proposal_view(
        proposal,
        page=page,
        current_content_md=current.content_md if current else "",
        parent_slug=None,
    )


async def get_wiki_proposal(
    user: KeycloakUser,
    team_id: TeamId,
    proposal_id: str,
    deps: ProductServiceDependencies,
) -> WikiProposal:
    """What the approval modal reads to render the diff."""

    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    proposal = await store.get_proposal(team_id, proposal_id)
    if proposal is None:
        raise WikiRequestError("This proposal is no longer pending.", http_status=404)
    page = await store.get_page(team_id, proposal.page_id)
    current = (
        await store.get_revision(team_id, page.current_revision_id)
        if page and page.current_revision_id
        else None
    )
    parent_slug = None
    if page is None and proposal.proposed_parent_page_id:
        parent = await store.get_page(team_id, proposal.proposed_parent_page_id)
        parent_slug = parent.slug if parent else None
    return _proposal_view(
        proposal,
        page=page,
        current_content_md=current.content_md if current else "",
        parent_slug=parent_slug,
    )


async def publish_wiki_proposal(
    user: KeycloakUser,
    team_id: TeamId,
    proposal_id: str,
    deps: ProductServiceDependencies,
) -> WikiPageDetail:
    """Approve a pending proposal. The approver becomes the author of record.

    The page keeps its review mark: approving says the change is wanted, not
    that the whole page has been read.
    """

    team_id = await _require_wiki_access(user, team_id, deps, [WIKI_READ_PERMISSION])
    store = deps.get_team_wiki_store()
    proposal = await store.get_proposal(team_id, proposal_id)
    if proposal is None:
        raise WikiRequestError("This proposal is no longer pending.", http_status=404)

    slug = ""
    if proposal.proposed_title is not None:
        # Re-run what proposing checked. A proposal can wait, and the tree can
        # move under it: the parent may be gone (publish at the root rather than
        # dangle) or have been pushed deeper (refuse rather than break the cap).
        pages = {p.page_id: p for p in await store.list_pages(team_id)}
        parent_id = proposal.proposed_parent_page_id
        if parent_id is not None and parent_id not in pages:
            parent_id = None
        if _child_depth_under(pages, parent_id) > MAX_PAGE_DEPTH:
            raise WikiRequestError(
                f"A wiki page cannot sit deeper than {MAX_PAGE_DEPTH} levels. "
                "The page this one would go under has moved since it was "
                "proposed.",
                http_status=409,
            )
        if parent_id != proposal.proposed_parent_page_id:
            await store.reparent_proposal(
                team_id=team_id, revision_id=proposal_id, parent_page_id=parent_id
            )
        slug = await _unique_slug(store, team_id, proposal.proposed_title)
    try:
        page = await store.publish_proposal(
            team_id=team_id,
            revision_id=proposal_id,
            slug=slug,
            approver_user_id=user.uid,
        )
    except _StaleBaseWrite:
        # Someone edited the page while the proposal waited for an answer.
        # Refusing carries the current text so the agent can redo its edit on
        # top of it rather than the approver losing the other person's work.
        current_page = await store.get_page(team_id, proposal.page_id)
        current_id = current_page.current_revision_id if current_page else None
        current = await store.get_revision(team_id, current_id) if current_id else None
        raise WikiConflictError(
            current_id or "", current.content_md if current else ""
        ) from None
    except WikiPageNotFoundError as exc:
        raise WikiRequestError(
            "The page this proposal targets no longer exists.", http_status=404
        ) from exc
    except WikiSlugAlreadyExistsError as exc:
        # The slug was free a moment ago. Someone else took it, or this same
        # proposal is being published twice at once — either way the caller can
        # act on a 409, where a 500 tells them nothing.
        raise WikiRequestError(
            "A page with this title already exists.", http_status=409
        ) from exc
    return WikiPageDetail(
        page=_summary(page),
        content_md=proposal.content_md,
        revision_id=proposal_id,
        author_kind="agent",
    )
