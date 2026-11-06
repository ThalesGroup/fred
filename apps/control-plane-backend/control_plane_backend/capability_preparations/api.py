# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Team-scoped preparation status and workload-scoped worker endpoints."""

from __future__ import annotations

import asyncio
import hmac
import json
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
)
from fred_core import (
    KeycloakUser,
    TeamPermission,
    get_principal_context,
    is_service_agent,
    require_own_credential,
)
from fred_core.common import TeamId
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, PrincipalContext
from fred_sdk.contracts.capability.preparation import PreparationWork
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.admission import (
    cleanup_staged_assets,
    stage_assets,
)
from control_plane_backend.capability_preparations.platform import (
    platform_selection_status,
    refresh_platform_candidate,
    reset_platform_selection,
    retry_platform_candidate,
    set_platform_selection_settings,
    start_platform_candidate,
)
from control_plane_backend.capability_preparations.schemas import (
    CleanupBatch,
    CleanupCompletion,
    PlatformPreparationSelection,
    PreparationStatus,
    PreparationStatusPage,
    WorkerAttemptResponse,
    WorkerPreparationResult,
    WorkerResultAck,
)
from control_plane_backend.capability_preparations.service import (
    begin_worker_attempt,
    claim_cleanup,
    finish_cleanup,
    get_work_asset,
    get_worker_work,
    list_agent_preparations,
    publish_worker_result,
    retry_agent_preparation,
)
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)
from control_plane_backend.organization_authz import require_manage_capabilities
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


async def _platform_view(
    deps: ProductServiceDependencies,
    runtime_id: str,
    capability_id: str,
    slot_key: str,
) -> PlatformPreparationSelection:
    async with _sessions(deps)() as session:
        active, candidate, settings = await platform_selection_status(
            session,
            runtime_id=runtime_id,
            capability_id=capability_id,
            slot_key=slot_key,
        )
    return PlatformPreparationSelection(
        active=active, candidate=candidate, settings=settings
    )


async def _platform_declaration(
    deps: ProductServiceDependencies, runtime_id: str, capability_id: str
):
    source = next(
        (
            source
            for source in deps.configuration.platform.runtime_catalog_sources
            if source.runtime_id == runtime_id
            and source.enabled
            and source.preparation_enabled
        ),
        None,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Runtime preparation unavailable")
    from control_plane_backend.product.service import _available_capabilities_for_source

    entries = await _available_capabilities_for_source(source.base_url)
    entry = next((entry for entry in entries if entry.id == capability_id), None)
    if entry is None or entry.preparation is None:
        raise HTTPException(
            status_code=404, detail="Capability preparation unavailable"
        )
    return entry


@router.get(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}",
    response_model=PlatformPreparationSelection,
)
async def get_platform_capability_preparation(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    del user
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


@router.put(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}/candidate",
    response_model=PlatformPreparationSelection,
)
async def put_platform_capability_candidate(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    deps: Dependencies,
    file: UploadFile = File(...),
    config_json: str = Form("{}"),
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    if deps.get_content_store is None:
        raise HTTPException(status_code=503, detail="Asset storage unavailable")
    entry = await _platform_declaration(deps, runtime_id, capability_id)
    spec = entry.preparation
    assert spec is not None
    if slot_key not in spec.asset_slots:
        raise HTTPException(status_code=422, detail="Undeclared preparation asset slot")
    content = await file.read(min(spec.max_input_bytes, 64 * 1024 * 1024) + 1)
    if len(content) > spec.max_input_bytes:
        raise HTTPException(status_code=413, detail="Preparation asset is too large")
    if len(config_json.encode()) > 128 * 1024:
        raise HTTPException(status_code=413, detail="Preparation config is too large")
    try:
        config = json.loads(config_json)
        if not isinstance(config, dict):
            raise ValueError("Preparation config must be an object")
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Invalid preparation config"
        ) from exc
    content_store = deps.get_content_store()
    staged = []
    try:
        staged = await stage_assets(
            content_store,
            available=[entry],
            selected_ids=[capability_id],
            uploads={
                capability_id: [
                    SimpleNamespace(
                        slot_key=slot_key,
                        filename=file.filename or "source",
                        content=content,
                        content_type=file.content_type,
                    )
                ]
            },
        )
        async with _sessions(deps)() as session:
            async with session.begin():
                await start_platform_candidate(
                    session,
                    runtime_id=runtime_id,
                    capability_id=capability_id,
                    slot_key=slot_key,
                    spec=spec,
                    config=config,
                    staged=staged[0],
                )
    except ValueError as exc:
        await cleanup_staged_assets(content_store, staged)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        await cleanup_staged_assets(content_store, staged)
        raise
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


@router.post(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}/candidate/retry",
    response_model=PlatformPreparationSelection,
)
async def post_platform_capability_candidate_retry(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    async with _sessions(deps)() as session:
        async with session.begin():
            try:
                row = await retry_platform_candidate(
                    session,
                    runtime_id=runtime_id,
                    capability_id=capability_id,
                    slot_key=slot_key,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


@router.post(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}/candidate/refresh",
    response_model=PlatformPreparationSelection,
)
async def post_platform_capability_candidate_refresh(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    config: dict[str, object],
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    entry = await _platform_declaration(deps, runtime_id, capability_id)
    spec = entry.preparation
    assert spec is not None
    if slot_key not in spec.asset_slots:
        raise HTTPException(status_code=422, detail="Undeclared preparation asset slot")
    async with _sessions(deps)() as session:
        async with session.begin():
            try:
                row = await refresh_platform_candidate(
                    session,
                    runtime_id=runtime_id,
                    capability_id=capability_id,
                    slot_key=slot_key,
                    spec=spec,
                    config=config,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="No platform template")
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


@router.delete(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}",
    response_model=PlatformPreparationSelection,
)
async def delete_platform_capability_preparation(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    async with _sessions(deps)() as session:
        async with session.begin():
            await reset_platform_selection(
                session,
                runtime_id=runtime_id,
                capability_id=capability_id,
                slot_key=slot_key,
            )
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


@router.put(
    "/platform/capability-preparations/{runtime_id}/{capability_id}/{slot_key}/settings",
    response_model=PlatformPreparationSelection,
)
async def put_platform_capability_settings(
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    settings: dict[str, object],
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> PlatformPreparationSelection:
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    async with _sessions(deps)() as session:
        async with session.begin():
            try:
                await set_platform_selection_settings(
                    session,
                    runtime_id=runtime_id,
                    capability_id=capability_id,
                    slot_key=slot_key,
                    settings=settings,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _platform_view(deps, runtime_id, capability_id, slot_key)


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
    row = await session.get(CapabilityPreparationRow, preparation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Preparation not found")
    _require_runtime_worker(deps, principals, row.runtime_id)
    return row


async def _require_job(
    session: AsyncSession,
    deps: ProductServiceDependencies,
    principals: PrincipalContext,
    preparation_id: str,
    worker_token: str | None,
) -> CapabilityPreparationRow:
    row = await _require_worker(session, deps, principals, preparation_id)
    if worker_token is None or not hmac.compare_digest(row.worker_token, worker_token):
        raise HTTPException(status_code=404, detail="Preparation not found")
    return row


def _require_runtime_worker(
    deps: ProductServiceDependencies,
    principals: PrincipalContext,
    runtime_id: str,
) -> None:
    if deps.configuration.security.m2m.enabled:
        if not is_service_agent(principals.caller):
            raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
    elif principals.caller.client_id != LOCAL_DEV_CLIENT_ID:
        raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
    source = next(
        (
            source
            for source in deps.configuration.platform.runtime_catalog_sources
            if source.runtime_id == runtime_id and source.enabled
        ),
        None,
    )
    if (
        source is None
        or source.preparation_client_id is None
        or source.preparation_client_id != principals.caller.client_id
    ):
        raise HTTPException(status_code=404, detail="Preparation not found")


@router.post(
    "/internal/capability-preparations/cleanup/claim", response_model=CleanupBatch
)
async def claim_capability_cleanup(
    runtime_id: Annotated[str, Query(min_length=1)],
    deps: Dependencies,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
    principals: PrincipalContext = Depends(get_principal_context),
) -> CleanupBatch:
    _require_runtime_worker(deps, principals, runtime_id)
    async with _sessions(deps)() as session:
        async with session.begin():
            items = await claim_cleanup(session, runtime_id=runtime_id, limit=limit)
    return CleanupBatch(items=items)


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
    worker_token: Annotated[str | None, Header(alias="X-Preparation-Token")] = None,
) -> PreparationWork:
    async with _sessions(deps)() as session:
        await _require_job(session, deps, principals, str(preparation_id), worker_token)
        work = await get_worker_work(session, str(preparation_id))
    if work is None:
        raise HTTPException(status_code=404, detail="Preparation not found")
    return work


@router.post(
    "/internal/capability-preparations/{preparation_id}/attempts/{attempt}",
    response_model=WorkerAttemptResponse,
)
async def post_capability_preparation_attempt(
    preparation_id: UUID,
    attempt: Annotated[int, Path(ge=1, le=10)],
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
    worker_token: Annotated[str | None, Header(alias="X-Preparation-Token")] = None,
) -> WorkerAttemptResponse:
    async with _sessions(deps)() as session:
        async with session.begin():
            await _require_job(
                session, deps, principals, str(preparation_id), worker_token
            )
            work = await begin_worker_attempt(
                session, preparation_id=str(preparation_id), attempt=attempt
            )
    return WorkerAttemptResponse(work=work)


@router.get(
    "/internal/capability-preparations/{preparation_id}/assets/{asset_id}",
    response_class=Response,
)
async def get_capability_preparation_asset(
    preparation_id: UUID,
    asset_id: UUID,
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
    worker_token: Annotated[str | None, Header(alias="X-Preparation-Token")] = None,
) -> Response:
    async with _sessions(deps)() as session:
        await _require_job(session, deps, principals, str(preparation_id), worker_token)
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
    worker_token: Annotated[str | None, Header(alias="X-Preparation-Token")] = None,
) -> WorkerResultAck:
    async with _sessions(deps)() as session:
        async with session.begin():
            await _require_job(
                session, deps, principals, str(preparation_id), worker_token
            )
            try:
                accepted = await publish_worker_result(
                    session, preparation_id=str(preparation_id), completion=body
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WorkerResultAck(accepted=accepted)


@router.post(
    "/internal/capability-preparations/{preparation_id}/cleanup/complete",
    response_model=WorkerResultAck,
)
async def complete_capability_cleanup(
    preparation_id: UUID,
    body: CleanupCompletion,
    deps: Dependencies,
    principals: PrincipalContext = Depends(get_principal_context),
) -> WorkerResultAck:
    if deps.get_content_store is None:
        raise HTTPException(status_code=503, detail="Asset storage is unavailable")
    async with _sessions(deps)() as session:
        async with session.begin():
            await _require_worker(session, deps, principals, str(preparation_id))
            accepted = await finish_cleanup(
                session,
                preparation_id=str(preparation_id),
                claim_id=str(body.claim_id),
                content_store=deps.get_content_store(),
            )
    return WorkerResultAck(accepted=accepted)
