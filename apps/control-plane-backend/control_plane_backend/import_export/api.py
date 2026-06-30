"""Import/export endpoints for platform configuration snapshots.

The import endpoint accepts kea-format snapshot zips (the format produced by the
kea admin `/admin/migration` export feature), but is designed to be the canonical
configuration backup/restore mechanism for swift — not a one-shot migration tool.

Typical use-cases:
- Migrating business configuration from kea to swift (initial cutover)
- Per-team configuration backup and restore
- Copying an agent/prompt library between swift environments

All endpoints require platform admin access.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    RebacEngine,
    get_current_user,
)
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory
from fred_core.tasks.models import MigrationTaskEvent, StartMigrationRequest, TaskState
from fred_core.tasks.service import TaskService
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.import_export.bundle import open_bundle
from control_plane_backend.import_export.exporter import run_export
from control_plane_backend.import_export.importer import run_import
from control_plane_backend.import_export.stats import (
    PlatformStats,
    compute_platform_stats,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — realistic snapshots are well under 10 MB


class ImportLaunchResponse(BaseModel):
    task_id: str
    import_id: str


class ResetLaunchResponse(BaseModel):
    task_id: str


def _get_task_service(request: Request) -> TaskService:
    return get_application_container(request).get_task_service()


def _get_engine(request: Request) -> AsyncEngine:
    return get_application_container(request).get_pg_async_engine()


def _get_agent_instance_store(request: Request) -> AgentInstanceStore:
    return get_application_container(request).get_agent_instance_store()


def _get_rebac_engine(request: Request) -> RebacEngine:
    return get_application_container(request).get_rebac_engine()


def build_import_export_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["import-export"])

    @router.post(
        "/import-export/import",
        status_code=202,
        response_model=ImportLaunchResponse,
        summary="Import a configuration snapshot",
        description=(
            "Upload a configuration snapshot zip and import it into this swift instance.\n\n"
            "**Accepted formats:**\n"
            "- Kea snapshot v1 (produced by kea `/admin/migration` export)\n\n"
            "**What is imported:**\n"
            "- Agent instances (kea agents mapped to their swift template equivalent)\n\n"
            "**What is skipped with a warning:**\n"
            "- Document metadata (content/vectors not in the zip — mirror separately)\n"
            "- Tags (knowledge-flow import path not yet implemented)\n"
            "- MCP servers (re-seeded by deployment)\n\n"
            "Progress is streamed via `GET /tasks/{task_id}/events`.\n\n"
            "**Platform admin only.**"
        ),
    )
    async def import_snapshot(
        file: UploadFile,
        background_tasks: BackgroundTasks,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        task_service: Annotated[TaskService, Depends(_get_task_service)],
        engine: Annotated[AsyncEngine, Depends(_get_engine)],
        agent_instance_store: Annotated[
            AgentInstanceStore, Depends(_get_agent_instance_store)
        ],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
        label: Annotated[str | None, Form()] = None,
    ) -> ImportLaunchResponse:
        await rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)

        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(
                status_code=400, detail="A .zip snapshot file is required"
            )

        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Snapshot exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
            )
        import_id = str(uuid.uuid4())

        start_response = await task_service.start(
            StartMigrationRequest(),
            created_by=user.uid,
        )
        task_id = start_response.task_id

        async def _run() -> None:
            try:
                bundle = open_bundle(data)
                await run_import(
                    bundle=bundle,
                    import_id=import_id,
                    task_id=task_id,
                    task_service=task_service,
                    engine=engine,
                    agent_instance_store=agent_instance_store,
                )
                await task_service.record(
                    MigrationTaskEvent(
                        task_id=task_id,
                        state=TaskState.succeeded,
                        seq=0,
                        timestamp=datetime.now(timezone.utc),
                    )
                )
                logger.info("[import-export] import %s completed", import_id)
            except Exception as exc:
                logger.exception("[import-export] import %s failed: %s", import_id, exc)
                await task_service.fail_task(task_id, str(exc))

        background_tasks.add_task(_run)
        return ImportLaunchResponse(task_id=task_id, import_id=import_id)

    @router.get(
        "/import-export/export",
        summary="Export a configuration snapshot",
        description=(
            "Download a swift-native `.zip` snapshot of this instance's agent "
            "instances, knowledge tags, and document metadata.\n\n"
            "The snapshot is re-importable through the import endpoint "
            "(`source_platform=swift`), enabling export → reset → import cycles.\n\n"
            "Object-store binaries, vector embeddings, Keycloak users, and OpenFGA "
            "tuples are NOT included (mirrored / preserved separately).\n\n"
            "**Platform admin only.**"
        ),
        responses={200: {"content": {"application/zip": {}}}},
    )
    async def export_snapshot(
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        engine: Annotated[AsyncEngine, Depends(_get_engine)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> Response:
        await rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
        data = await run_export(engine)
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="swift-snapshot.zip"'
            },
        )

    @router.get(
        "/import-export/stats",
        response_model=PlatformStats,
        summary="Platform data summary",
        description=(
            "Aggregate counts of teams, members (by OWNER / MANAGER / MEMBER role), "
            "agent instances, and prompts currently stored in this swift instance.\n\n"
            "A relational overview (distinct from the OpenSearch KPI dashboard), shown "
            "as a reassurance panel alongside import / export / reset.\n\n"
            "**Platform admin only.**"
        ),
    )
    async def platform_stats(
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        team_deps: Annotated[
            TeamServiceDependencies, Depends(get_team_service_dependencies)
        ],
        engine: Annotated[AsyncEngine, Depends(_get_engine)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> PlatformStats:
        await rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)
        return await compute_platform_stats(
            user=user,
            team_deps=team_deps,
            engine=engine,
        )

    @router.post(
        "/import-export/reset",
        status_code=202,
        response_model=ResetLaunchResponse,
        summary="Reset all imported platform data",
        description=(
            "Delete all agent instances, knowledge tags, and document metadata rows from "
            "this swift instance in a single atomic transaction. Object-store binaries, "
            "vector embeddings, Keycloak users, and OpenFGA tuples are NOT touched.\n\n"
            "Progress is streamed via `GET /tasks/{task_id}/events`.\n\n"
            "**This action is irreversible. Intended for integration / test environments "
            "to support export → reset → import test cycles.**\n\n"
            "**Platform admin only.**"
        ),
    )
    async def reset_platform_data(
        background_tasks: BackgroundTasks,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        task_service: Annotated[TaskService, Depends(_get_task_service)],
        engine: Annotated[AsyncEngine, Depends(_get_engine)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> ResetLaunchResponse:
        await rebac.check_user_permission_or_raise(user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID)

        start_response = await task_service.start(
            StartMigrationRequest(),
            created_by=user.uid,
        )
        task_id = start_response.task_id

        async def _run() -> None:
            try:
                await task_service.record(
                    MigrationTaskEvent(
                        task_id=task_id,
                        state=TaskState.running,
                        seq=0,
                        timestamp=datetime.now(timezone.utc),
                        step="Réinitialisation en cours…",
                    )
                )
                session_factory = make_session_factory(engine)
                async with session_factory() as session:
                    async with session.begin():
                        agents_result = await session.execute(
                            delete(AgentInstanceRow).execution_options(
                                synchronize_session=False
                            )
                        )
                        tags_result = await session.execute(
                            delete(TagRow).execution_options(synchronize_session=False)
                        )
                        docs_result = await session.execute(
                            delete(DocumentMetadataRow).execution_options(
                                synchronize_session=False
                            )
                        )
                summary = (
                    f"{getattr(agents_result, 'rowcount', 0)} agents, "
                    f"{getattr(tags_result, 'rowcount', 0)} tags, "
                    f"{getattr(docs_result, 'rowcount', 0)} documents supprimés"
                )
                logger.warning("[import-export] reset by %s: %s", user.uid, summary)
                await task_service.record(
                    MigrationTaskEvent(
                        task_id=task_id,
                        state=TaskState.running,
                        seq=0,
                        timestamp=datetime.now(timezone.utc),
                        step=summary,
                        progress=1.0,
                    )
                )
                await task_service.record(
                    MigrationTaskEvent(
                        task_id=task_id,
                        state=TaskState.succeeded,
                        seq=0,
                        timestamp=datetime.now(timezone.utc),
                    )
                )
            except Exception as exc:
                logger.exception("[import-export] reset failed: %s", exc)
                await task_service.fail_task(task_id, str(exc))

        background_tasks.add_task(_run)
        return ResetLaunchResponse(task_id=task_id)

    return router
