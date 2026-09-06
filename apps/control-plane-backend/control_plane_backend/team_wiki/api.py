from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, Response, status
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.team_wiki.schemas import (
    CreateWikiPageRequest,
    SetNeedsReviewRequest,
    UpdateWikiPageContentRequest,
    UpdateWikiPageMetadataRequest,
    UpdateWikiRulesRequest,
    WikiAvailability,
    WikiPageDetail,
    WikiPageSummary,
    WikiPageTree,
    WikiRevisionList,
)
from control_plane_backend.team_wiki.service import (
    WikiConflictError,
    WikiRequestError,
    create_wiki_page,
    delete_wiki_page,
    get_wiki_availability,
    get_wiki_page,
    get_wiki_rules,
    get_wiki_tree,
    list_wiki_revisions,
    restore_wiki_revision,
    set_wiki_page_needs_review,
    update_wiki_page_content,
    update_wiki_page_metadata,
    update_wiki_rules,
)

router = APIRouter(tags=["Teams"])

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
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "current_revision_id": exc.current_revision_id,
                "current_content_md": exc.current_content_md,
            },
        )


@router.get(
    "/teams/{team_id}/wiki/availability",
    response_model=WikiAvailability,
    summary="Whether this team has a wiki (WIKI-03)",
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
    summary="List one team's wiki pages (WIKI-01)",
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
    summary="Read the team's wiki rules page (WIKI-01)",
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
    summary="Update the team's wiki rules page (WIKI-01)",
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
    summary="Read one wiki page by slug (WIKI-01)",
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
    summary="Create one wiki page (WIKI-01)",
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
    summary="Publish a new revision of one wiki page (WIKI-01)",
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
    summary="Rename or move one wiki page (WIKI-01)",
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
    summary="Set or clear one wiki page's review mark (WIKI-01)",
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
    summary="List one wiki page's revisions (WIKI-01)",
)
async def list_revisions(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> WikiRevisionList:
    return await list_wiki_revisions(user, team_id, page_id, deps)


@router.post(
    "/teams/{team_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore",
    response_model=WikiPageDetail,
    summary="Restore one earlier revision of a wiki page (WIKI-01)",
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
    summary="Delete one wiki page (WIKI-01)",
)
async def delete_page(
    team_id: Annotated[TeamId, Path()],
    page_id: Annotated[str, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    await delete_wiki_page(user, team_id, page_id, deps)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
