# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fred_core import (
    KeycloakUser,
    TeamPermission,
    get_current_user,
    require_own_credential,
)
from fred_core.common import TeamId

from control_plane_backend.agent_marketplace import service
from control_plane_backend.agent_marketplace.schemas import (
    MarketplaceAgentDetail,
    MarketplaceAgentImportRequest,
    MarketplaceAgentImportResponse,
    MarketplaceAgentImportTargetsResponse,
    MarketplaceAgentSummary,
    PublishAgentRequest,
    UnpublishAgentRequest,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.product.schemas import AgentMarketplaceState
from control_plane_backend.teams.service import require_team_access

router = APIRouter(tags=["AgentMarketplace"])
ProductDependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]
_AGENT_PATH = "/teams/{team_id}/agent-instances/{agent_instance_id}"
T = TypeVar("T")


async def _run(call: Awaitable[T]) -> T:
    try:
        return await call
    except service.MarketplaceError as exc:
        detail: dict[str, str] = {"code": exc.code, "message": str(exc)}
        if exc.capability_id is not None:
            detail["capability_id"] = exc.capability_id
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc


@router.post(
    f"{_AGENT_PATH}/publish",
    response_model=AgentMarketplaceState,
    response_model_exclude_none=True,
    summary="Publish or republish an agent to the agents marketplace (editors).",
)
async def post_agent_publish(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    body: PublishAgentRequest,
    deps: ProductDependencies,
    http_request: Request,
    user: KeycloakUser = Depends(require_own_credential),
) -> AgentMarketplaceState:
    """
    Store a snapshot of the agent as a copy to another team would carry it.

    409 when the team is private, publication is disabled for it, its quota is
    reached (new publications only), the agent type is not public, the agent
    is deactivated or suspended (`marketplace_agent_inactive`), or
    `expected_version` is stale. A failed export keeps the previous snapshot:
    422 for a capability cause, 503 for an unreachable or failing pod.
    """
    return await _run(
        service.publish_agent(
            user=user,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            request=body,
            deps=deps,
            authorization=http_request.headers.get("Authorization"),
        )
    )


@router.post(
    f"{_AGENT_PATH}/unpublish",
    status_code=204,
    response_model=None,
    summary="Remove an agent from the marketplace (editors, team admin, platform admin).",
)
async def post_agent_unpublish(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    body: UnpublishAgentRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """`reason` is accepted from a platform admin only (403 otherwise)."""
    await _run(
        service.unpublish_agent(
            user=user,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            request=body,
            deps=deps,
        )
    )


@router.post(
    f"{_AGENT_PATH}/marketplace-dismiss",
    status_code=204,
    response_model=None,
    summary="Hide an agent's Removed marketplace state for its team (editors, team admin).",
)
async def post_agent_marketplace_dismiss(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await _run(
        service.dismiss_marketplace_removal(
            user=user, team_id=team_id, agent_instance_id=agent_instance_id, deps=deps
        )
    )


@router.get(
    "/marketplace/agents",
    response_model=list[MarketplaceAgentSummary],
    summary="List published agents, newest first publication first.",
)
async def get_marketplace_agents(
    deps: ProductDependencies,
    q: Annotated[str | None, Query(max_length=200)] = None,
    team_id: Annotated[TeamId | None, Query()] = None,
    user: KeycloakUser = Depends(get_current_user),
) -> list[MarketplaceAgentSummary]:
    return await service.list_marketplace_agents(
        user=user, q=q, team_id=team_id, deps=deps
    )


@router.get(
    "/marketplace/agents/{entry_id}",
    response_model=MarketplaceAgentDetail,
    summary="Read-only detail of a published agent (files as name and size only).",
)
async def get_marketplace_agent(
    entry_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceAgentDetail:
    return await _run(
        service.get_marketplace_agent(user=user, entry_id=entry_id, deps=deps)
    )


@router.put(
    "/marketplace/agents/{entry_id}/like",
    response_model=MarketplaceAgentSummary,
    summary="Like a published agent (idempotent).",
)
async def put_marketplace_agent_like(
    entry_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceAgentSummary:
    return await _run(
        service.set_marketplace_like(
            user=user, entry_id=entry_id, liked=True, deps=deps
        )
    )


@router.delete(
    "/marketplace/agents/{entry_id}/like",
    response_model=MarketplaceAgentSummary,
    summary="Remove one's like of a published agent (idempotent).",
)
async def delete_marketplace_agent_like(
    entry_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceAgentSummary:
    return await _run(
        service.set_marketplace_like(
            user=user, entry_id=entry_id, liked=False, deps=deps
        )
    )


@router.get(
    "/marketplace/agents/{entry_id}/import-targets",
    response_model=MarketplaceAgentImportTargetsResponse,
    summary="Where a published agent can be imported, with each destination's readiness.",
)
async def get_marketplace_agent_import_targets(
    entry_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceAgentImportTargetsResponse:
    """Personal space and teams where the caller updates agents, publishing team excluded."""
    targets = await _run(
        service.list_marketplace_import_targets(user=user, entry_id=entry_id, deps=deps)
    )
    return MarketplaceAgentImportTargetsResponse(targets=targets)


@router.post(
    "/marketplace/agents/{entry_id}/import",
    response_model=MarketplaceAgentImportResponse,
    response_model_exclude_none=True,
    summary="Import a published agent into one or more of the caller's spaces.",
)
async def post_marketplace_agent_import(
    entry_id: Annotated[str, Path(min_length=1)],
    body: MarketplaceAgentImportRequest,
    deps: ProductDependencies,
    http_request: Request,
    user: KeycloakUser = Depends(require_own_credential),
) -> MarketplaceAgentImportResponse:
    """Each destination is handled on its own; the publishing team is refused."""

    async def require_editor(target_team_id: TeamId) -> TeamId:
        return await require_team_access(
            user,
            target_team_id,
            deps.team_dependencies,
            required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
        )

    results = await _run(
        service.import_marketplace_agent(
            user=user,
            entry_id=entry_id,
            target_team_ids=body.target_team_ids,
            deps=deps,
            authorization=http_request.headers.get("Authorization"),
            require_editor=require_editor,
            locale=body.locale,
        )
    )
    return MarketplaceAgentImportResponse(results=results)
