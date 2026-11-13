# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Author-scoped temporary preparation routes for agent forms."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    UploadFile,
)
from fred_core import KeycloakUser, TeamPermission, require_own_credential
from fred_core.common import TeamId

from control_plane_backend.capabilities.authz import can_team_use_capability
from control_plane_backend.capability_preparations.admission import (
    cleanup_staged_assets,
    stage_assets,
)
from control_plane_backend.capability_preparations.drafts import (
    create_draft,
    discard_draft,
    draft_expired,
    draft_status,
    get_author_draft,
    retry_draft,
)
from control_plane_backend.capability_preparations.schemas import DraftPreparationStatus
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.product.service import (
    CapabilityAssetFile,
    EnrollmentError,
    _fetch_runtime_templates,
    _resolve_enrollable_template,
    _validate_capability_config_via_pod,
    capability_gate_exempt,
    template_capability_id,
)
from control_plane_backend.teams.service import require_team_access

router = APIRouter(tags=["Capability Preparations"])
Dependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


def _sessions(deps: ProductServiceDependencies):
    if deps.get_sql_session_factory is None:
        raise HTTPException(status_code=503, detail="Preparation database unavailable")
    return deps.get_sql_session_factory()


async def _target_entry(
    deps: ProductServiceDependencies,
    *,
    user: KeycloakUser,
    team_id: TeamId,
    target_kind: str,
    target_id: str,
    capability_id: str,
):
    if target_kind == "template":
        try:
            source, template = await _resolve_enrollable_template(
                user=user, team_id=team_id, template_id=target_id, deps=deps
            )
        except EnrollmentError as exc:
            raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    elif target_kind == "agent":
        record = await deps.get_agent_instance_store().get_for_team(target_id, team_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Agent instance not found")
        source = next(
            (
                item
                for item in deps.configuration.platform.runtime_catalog_sources
                if item.runtime_id == record.source_runtime_id and item.enabled
            ),
            None,
        )
        if source is None:
            raise HTTPException(status_code=503, detail="Runtime source unavailable")
        if not capability_gate_exempt(
            record.source_agent_id
        ) and not await can_team_use_capability(
            deps.team_dependencies.rebac,
            team_id,
            capability_id=template_capability_id(
                record.source_runtime_id, record.source_agent_id
            ),
        ):
            raise HTTPException(status_code=404, detail="Agent template unavailable")
        try:
            templates = await _fetch_runtime_templates(
                source.base_url, include_non_public=True
            )
        except EnrollmentError as exc:
            raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
        template = next(
            (
                item
                for item in templates
                if item.template_agent_id == record.source_agent_id
            ),
            None,
        )
        if template is None:
            raise HTTPException(status_code=404, detail="Agent template unavailable")
    else:
        raise HTTPException(status_code=422, detail="Invalid draft target kind")
    if not source.preparation_enabled:
        raise HTTPException(status_code=404, detail="Runtime preparation unavailable")
    entry = next(
        (item for item in template.available_capabilities if item.id == capability_id),
        None,
    )
    if (
        entry is None
        or entry.preparation is None
        or not entry.preparation.supports_drafts
    ):
        raise HTTPException(status_code=404, detail="Draft preparation unavailable")
    if not await can_team_use_capability(
        deps.team_dependencies.rebac, team_id, capability_id=capability_id
    ):
        raise HTTPException(status_code=404, detail="Draft preparation unavailable")
    return source, entry


@router.post(
    "/teams/{team_id}/capability-preparation-drafts",
    response_model=DraftPreparationStatus,
    status_code=201,
)
async def post_team_capability_preparation_draft(
    team_id: Annotated[TeamId, Path()],
    deps: Dependencies,
    http_request: Request,
    target_kind: Annotated[str, Form()],
    target_id: Annotated[str, Form()],
    capability_id: Annotated[str, Form()],
    slot_key: Annotated[str, Form()],
    group_id: Annotated[UUID, Form()],
    generation: Annotated[int, Form(ge=1)],
    config_json: Annotated[str, Form()],
    file: UploadFile = File(...),
    user: KeycloakUser = Depends(require_own_credential),
) -> DraftPreparationStatus:
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    if deps.get_content_store is None:
        raise HTTPException(status_code=503, detail="Asset storage unavailable")
    source, entry = await _target_entry(
        deps,
        user=user,
        team_id=team_id,
        target_kind=target_kind,
        target_id=target_id,
        capability_id=capability_id,
    )
    spec = entry.preparation
    assert spec is not None
    if slot_key not in spec.asset_slots:
        raise HTTPException(status_code=422, detail="Undeclared preparation asset slot")
    if len(config_json.encode("utf-8")) > 128 * 1024:
        raise HTTPException(status_code=413, detail="Preparation config is too large")
    try:
        config = json.loads(config_json)
        if not isinstance(config, dict):
            raise ValueError("Preparation config must be an object")
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Invalid preparation config"
        ) from exc
    content = await file.read(spec.max_input_bytes + 1)
    if len(content) > spec.max_input_bytes:
        raise HTTPException(status_code=413, detail="Preparation asset is too large")
    upload = CapabilityAssetFile(
        slot_key=slot_key,
        filename=file.filename or "template.pptx",
        content=content,
        content_type=file.content_type,
    )
    try:
        envelope = await _validate_capability_config_via_pod(
            base_url=source.base_url,
            capability_id=capability_id,
            config_values=config,
            team_id=team_id,
            agent_instance_id=None,
            authorization=http_request.headers.get("Authorization"),
            asset_files=[upload],
        )
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    validated_config = envelope.get("config")
    if not isinstance(validated_config, dict):
        raise HTTPException(
            status_code=502, detail="Invalid validated preparation config"
        )
    content_store = deps.get_content_store()
    staged = []
    try:
        staged = await stage_assets(
            content_store,
            available=[entry],
            selected_ids=[capability_id],
            uploads={capability_id: [upload]},
        )
        async with _sessions(deps)() as session:
            async with session.begin():
                row = await create_draft(
                    session,
                    team_id=str(team_id),
                    author_id=user.uid,
                    target_id=f"{target_kind}:{target_id}",
                    group_id=str(group_id),
                    generation=generation,
                    runtime_id=source.runtime_id,
                    capability_id=capability_id,
                    spec=spec,
                    validated_config=validated_config,
                    staged=staged[0],
                )
            return await draft_status(session, row)
    except ValueError as exc:
        await cleanup_staged_assets(content_store, staged)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        await cleanup_staged_assets(content_store, staged)
        raise


async def _author_draft(
    deps: ProductServiceDependencies,
    *,
    team_id: TeamId,
    user: KeycloakUser,
):
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    return team_id


@router.get(
    "/teams/{team_id}/capability-preparation-drafts/{draft_id}",
    response_model=DraftPreparationStatus,
)
async def get_team_capability_preparation_draft(
    team_id: Annotated[TeamId, Path()],
    draft_id: UUID,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> DraftPreparationStatus:
    team_id = await _author_draft(deps, team_id=team_id, user=user)
    async with _sessions(deps)() as session:
        row = await get_author_draft(
            session, draft_id=str(draft_id), team_id=str(team_id), author_id=user.uid
        )
        if row is None or not row.is_current or draft_expired(row.draft_expires_at):
            raise HTTPException(status_code=404, detail="Draft not found")
        return await draft_status(session, row)


@router.post(
    "/teams/{team_id}/capability-preparation-drafts/{draft_id}/retry",
    response_model=DraftPreparationStatus,
)
async def post_team_capability_preparation_draft_retry(
    team_id: Annotated[TeamId, Path()],
    draft_id: UUID,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> DraftPreparationStatus:
    team_id = await _author_draft(deps, team_id=team_id, user=user)
    async with _sessions(deps)() as session:
        async with session.begin():
            row = await get_author_draft(
                session,
                draft_id=str(draft_id),
                team_id=str(team_id),
                author_id=user.uid,
                lock=True,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            try:
                next_row = await retry_draft(session, row)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return await draft_status(session, next_row)


@router.delete(
    "/teams/{team_id}/capability-preparation-drafts/{draft_id}",
    status_code=204,
)
async def delete_team_capability_preparation_draft(
    team_id: Annotated[TeamId, Path()],
    draft_id: UUID,
    deps: Dependencies,
    user: KeycloakUser = Depends(require_own_credential),
) -> None:
    team_id = await _author_draft(deps, team_id=team_id, user=user)
    async with _sessions(deps)() as session:
        async with session.begin():
            row = await get_author_draft(
                session,
                draft_id=str(draft_id),
                team_id=str(team_id),
                author_id=user.uid,
                lock=True,
            )
            if row is not None and row.is_current:
                discard_draft(row)
