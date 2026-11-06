# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Team-scoped preparation status and workload-scoped worker endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fred_core import (
    KeycloakUser,
    TeamPermission,
    get_principal_context,
    require_own_credential,
    require_workload_caller,
)
from fred_core.common import TeamId
from fred_core.security.structure import PrincipalContext
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID
from fred_sdk.contracts.capability.preparation import PreparationWork
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.schemas import (
    PreparationStatus,
    PreparationStatusPage,
    WorkerPreparationResult,
    WorkerResultAck,
)
from control_plane_backend.capability_preparations.service import (
    get_work_asset,
    get_worker_work,
    list_agent_preparations,
    publish_worker_result,
    retry_agent_preparation,
)
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.teams.service import require_team_access

router = APIRouter(tags=["Capability Preparations"])
Dependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


def _sessions(deps: ProductServiceDependencies):
    if deps.get_sql_session_factory is None:
        raise HTTPException(
            status_code=503, detail="Preparation database is unavailable"
        )
    return deps.get_sql_session_factory()


async def _require_agent(
    deps: ProductServiceDependencies, team_id: TeamId, agent_instance_id: str
) -> None:
    if (
        await deps.get_agent_instance_store().get_for_team(agent_instance_id, team_id)
        is None
    ):
        raise HTTPException(status_code=404, detail="Agent instance not found")


async def _require_worker(
    session: AsyncSession,
    deps: ProductServiceDependencies,
    principals: PrincipalContext,
    preparation_id: str,
) -> CapabilityPreparationRow:
    if deps.configuration.security.m2m.enabled:
        require_workload_caller(principals.caller)
    elif principals.caller.client_id != LOCAL_DEV_CLIENT_ID:
        raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
    row = await session.get(CapabilityPreparationRow, preparation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Preparation not found")
    source = next(
        (
            source
            for source in deps.configuration.platform.runtime_catalog_sources
            if source.runtime_id == row.runtime_id and source.enabled
        ),
        None,
    )
    if (
        source is None
        or source.preparation_client_id is None
        or source.preparation_client_id != principals.caller.client_id
    ):
        raise HTTPException(status_code=404, detail="Preparation not found")
    return row


@router.get(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/preparations",
    response_model=PreparationStatusPage,
)
async def get_team_agent_preparations(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: Dependencies,
    limit: Annotated[int, Query(ge=1, le=100)] = 32,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: KeycloakUser = Depends(require_own_credential),
) -> PreparationStatusPage:
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    await _require_agent(deps, team_id, agent_instance_id)
    async with _sessions(deps)() as session:
        return await list_agent_preparations(
            session,
            agent_instance_id=agent_instance_id,
            team_id=str(team_id),
            limit=limit,
            offset=offset,
        )


@router.post(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/preparations/{capability_id}/retry",
    response_model=PreparationStatus,
)
async def post_team_agent_preparation_retry(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    capability_id: Annotated[str, Path(min_length=1)],
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PreparationStatus:
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    await _require_agent(deps, team_id, agent_instance_id)
    async with _sessions(deps)() as session:
        async with session.begin():
            try:
                status = await retry_agent_preparation(
                    session,
                    agent_instance_id=agent_instance_id,
                    team_id=str(team_id),
                    capability_id=capability_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
    if status is None:
        raise HTTPException(status_code=404, detail="Preparation not found")
    return status


@router.get(
    "/internal/capability-preparations/{preparation_id}/work",
    response_model=PreparationWork,
)
async def get_capability_preparation_work(
    preparation_id: UUID,
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
) -> PreparationWork:
    async with _sessions(deps)() as session:
        await _require_worker(session, deps, principals, str(preparation_id))
        work = await get_worker_work(session, str(preparation_id))
    if work is None:
        raise HTTPException(status_code=404, detail="Preparation not found")
    return work


@router.get(
    "/internal/capability-preparations/{preparation_id}/assets/{asset_id}",
    response_class=Response,
)
async def get_capability_preparation_asset(
    preparation_id: UUID,
    asset_id: UUID,
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
) -> Response:
    async with _sessions(deps)() as session:
        await _require_worker(session, deps, principals, str(preparation_id))
        asset = await get_work_asset(
            session, preparation_id=str(preparation_id), asset_id=str(asset_id)
        )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if deps.get_content_store is None:
        raise HTTPException(status_code=503, detail="Asset storage is unavailable")
    content = await asyncio.to_thread(
        deps.get_content_store().read_object,
        asset.object_key,
        max_bytes=asset.size,
    )
    return Response(
        content=content,
        media_type=asset.content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/internal/capability-preparations/{preparation_id}/result",
    response_model=WorkerResultAck,
)
async def post_capability_preparation_result(
    preparation_id: UUID,
    body: WorkerPreparationResult,
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
) -> WorkerResultAck:
    async with _sessions(deps)() as session:
        async with session.begin():
            await _require_worker(session, deps, principals, str(preparation_id))
            try:
                accepted = await publish_worker_result(
                    session, preparation_id=str(preparation_id), completion=body
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WorkerResultAck(accepted=accepted)
