from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Response, status
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.team_wiki.schemas import (
    CreateWikiPageRequest,
    ProposeEditRequest,
    ProposePageRequest,
    SetNeedsReviewRequest,
    UpdateWikiPageContentRequest,
    UpdateWikiPageMetadataRequest,
    UpdateWikiRulesRequest,
    WikiAvailability,
    WikiConflictResponse,
    WikiPageDetail,
    WikiPageSummary,
    WikiPageTree,
    WikiProposal,
    WikiRevisionList,
)
from control_plane_backend.team_wiki.service import (
    WikiConflictError,
    WikiRequestError,
    create_wiki_page,
    delete_wiki_page,
    get_wiki_availability,
    get_wiki_page,
    get_wiki_proposal,
    get_wiki_rules,
    get_wiki_tree,
    list_wiki_revisions,
    propose_wiki_edit,
    propose_wiki_page,
    publish_wiki_proposal,
    restore_wiki_revision,
    set_wiki_page_needs_review,
    update_wiki_page_content,
    update_wiki_page_metadata,
    update_wiki_rules,
)

router = APIRouter(tags=["Teams"])

# A route that can raise WikiConflictError also always documents this shape for
# 409 — FastAPI's `responses` only takes one schema per status code, so a route
# that can also 409 for another reason (duplicate title, identical content,
# depth exceeded) says so in the description; those carry `detail` only, none
# of the fields below.
_REVISION_CONFLICT_RESPONSE = {
    "model": WikiConflictResponse,
    "description": (
        "The base revision is stale — the page moved on since it was read. "
        "Carries the current revision and content to rebase onto."
    ),
}
_DUPLICATE_TITLE_RESPONSE = {
    "description": "A sibling page already carries this title."
}

ProductDependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(WikiRequestError)
    async def wiki_request_error_handler(
        _request, exc: WikiRequestError
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(WikiConflictError)
    async def wiki_conflict_handler(_request, exc: WikiConflictError) -> JSONResponse:
        # 409 carries the current state, not just the refusal: the caller — a
        # human in the editor or an agent redoing its edit — needs something to
        # rebase onto, and a bare error forces a second round trip to get it.
        # Built from WikiConflictResponse so the wire body can never drift from
        # the schema declared on the routes below.
        body = WikiConflictResponse(
            detail=str(exc),
            current_revision_id=exc.current_revision_id,
            current_content_md=exc.current_content_md,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=body.model_dump(mode="json"),
        )


@router.get(
    "/teams/{team_id}/wiki/availability",
    response_model=WikiAvailability,
    summary="Whether this team has a wiki",
)
async def wiki_availability(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiAvailability:
    return await get_wiki_availability(user, team_id, deps)


@router.get(
    "/teams/{team_id}/wiki/pages",
    response_model=WikiPageTree,
    summary="List one team's wiki pages",
)
async def list_pages(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageTree:
    return await get_wiki_tree(user, team_id, deps)


@router.get(
    "/teams/{team_id}/wiki/rules",
    response_model=WikiPageDetail,
    summary="Read the team's wiki rules page",
)
async def read_rules(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await get_wiki_rules(user, team_id, deps)


@router.put(
    "/teams/{team_id}/wiki/rules",
    response_model=WikiPageDetail,
    summary="Update the team's wiki rules page",
    responses={
        409: {
            "model": WikiConflictResponse,
            "description": (
                "The base revision is stale — the page moved on since it was "
                "read. Carries the current revision and content to rebase "
                "onto. On this route only, the very first rules page can "
                "also 409 with `detail` only, when a root page is already "
                'titled "Rules".'
            ),
        }
    },
)
async def write_rules(
    team_id: Annotated[TeamId, Path()],
    request: UpdateWikiRulesRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await update_wiki_rules(user, team_id, request, deps)


@router.get(
    "/teams/{team_id}/wiki/pages/{slug}",
    response_model=WikiPageDetail,
    summary="Read one wiki page by slug",
)
async def read_page(
    team_id: Annotated[TeamId, Path()],
    slug: Annotated[str, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await get_wiki_page(user, team_id, slug, deps)


@router.post(
    "/teams/{team_id}/wiki/pages",
    response_model=WikiPageDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create one wiki page",
    responses={409: _DUPLICATE_TITLE_RESPONSE},
)
async def create_page(
    team_id: Annotated[TeamId, Path()],
    request: CreateWikiPageRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await create_wiki_page(user, team_id, request, deps)


@router.put(
    "/teams/{team_id}/wiki/pages/{page_id}/content",
    response_model=WikiPageDetail,
    summary="Publish a new revision of one wiki page",
    responses={409: _REVISION_CONFLICT_RESPONSE},
)
async def write_page_content(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    request: UpdateWikiPageContentRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await update_wiki_page_content(user, team_id, page_id, request, deps)


@router.patch(
    "/teams/{team_id}/wiki/pages/{page_id}",
    response_model=WikiPageSummary,
    summary="Rename or move one wiki page",
    responses={409: _DUPLICATE_TITLE_RESPONSE},
)
async def patch_page(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    request: UpdateWikiPageMetadataRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageSummary:
    return await update_wiki_page_metadata(user, team_id, page_id, request, deps)


@router.post(
    "/teams/{team_id}/wiki/pages/{page_id}/review",
    response_model=WikiPageSummary,
    summary="Set or clear one wiki page's review mark",
    responses={409: _REVISION_CONFLICT_RESPONSE},
)
async def set_review_mark(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    request: SetNeedsReviewRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageSummary:
    return await set_wiki_page_needs_review(user, team_id, page_id, request, deps)


@router.get(
    "/teams/{team_id}/wiki/pages/{page_id}/revisions",
    response_model=WikiRevisionList,
    summary="List one wiki page's revisions, newest first",
)
async def list_revisions(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    deps: ProductDependencies,
    cursor: Annotated[
        str | None,
        Query(
            description="From a previous response's `next_cursor`, to fetch older revisions."
        ),
    ] = None,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiRevisionList:
    return await list_wiki_revisions(user, team_id, page_id, deps, cursor=cursor)


@router.post(
    "/teams/{team_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore",
    response_model=WikiPageDetail,
    summary="Restore one earlier revision of a wiki page",
)
async def restore_revision(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    revision_id: Annotated[str, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await restore_wiki_revision(user, team_id, page_id, revision_id, deps)


@router.delete(
    "/teams/{team_id}/wiki/pages/{page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one wiki page",
    responses={
        409: {"description": "The page has children — delete or move them first."}
    },
)
async def delete_page(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    await delete_wiki_page(user, team_id, page_id, deps)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Agent proposals (WIKI-04) ---------------------------------------------
#
# Proposing changes nothing: a proposal is a stored suggestion, invisible in
# the wiki until a human publishes it. Which is why these are member-level
# rather than editor-level — the approval gate is the authority, not the role
# of whoever drove the agent.


@router.post(
    "/teams/{team_id}/wiki/proposals/page",
    response_model=WikiProposal,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a new wiki page through an agent",
)
async def propose_page(
    team_id: Annotated[TeamId, Path()],
    request: ProposePageRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiProposal:
    return await propose_wiki_page(user, team_id, request, deps)


@router.post(
    "/teams/{team_id}/wiki/proposals/edit",
    response_model=WikiProposal,
    status_code=status.HTTP_201_CREATED,
    summary="Propose an edit to a wiki page through an agent",
    responses={
        409: {
            "model": WikiConflictResponse,
            "description": (
                "The base revision is stale — the page moved on since it was "
                "read. Carries the current revision and content to redo the "
                "edit against. A proposal identical to the current text also "
                "409s on this route, with `detail` only."
            ),
        }
    },
)
async def propose_edit(
    team_id: Annotated[TeamId, Path()],
    request: ProposeEditRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiProposal:
    return await propose_wiki_edit(user, team_id, request, deps)


@router.get(
    "/teams/{team_id}/wiki/proposals/{proposal_id}",
    response_model=WikiProposal,
    summary="Read a pending proposal and the text it would replace",
)
async def read_proposal(
    team_id: Annotated[TeamId, Path()],
    proposal_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiProposal:
    return await get_wiki_proposal(user, team_id, proposal_id, deps)


@router.post(
    "/teams/{team_id}/wiki/proposals/{proposal_id}/publish",
    response_model=WikiPageDetail,
    summary="Approve a pending proposal and publish it",
    responses={
        409: {
            "model": WikiConflictResponse,
            "description": (
                "The page moved on since the proposal was written. Carries "
                "the current revision and content to redo the edit against. "
                "A duplicate title or a depth-limit breach also 409s on this "
                "route, with `detail` only."
            ),
        }
    },
)
async def publish_proposal(
    team_id: Annotated[TeamId, Path()],
    proposal_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiPageDetail:
    return await publish_wiki_proposal(user, team_id, proposal_id, deps)
