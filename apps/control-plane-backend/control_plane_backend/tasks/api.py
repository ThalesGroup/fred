from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Resource,
    TeamPermission,
    get_authenticated_caller,
    get_current_user,
    require_workload_caller,
)
from fred_core.common import TeamId
from fred_core.scheduler import (
    Schedule,
    delete_schedule_if_exists,
    ensure_schedule,
    to_temporal_spec,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunBudget,
    AgentRunScope,
    AgentRunWorkflowInputV1,
    ScheduledAgentRunInputV1,
    ScheduledAgentRunOccurrence,
    ScheduledAgentRunOccurrenceRequest,
)
from fred_core.tasks.authz import (
    authorize_task_access,
    authorize_task_mutation,
    authorize_task_stream,
    list_tasks_scoped,
)
from fred_core.tasks.models import (
    AcknowledgeTaskResponse,
    AgentRunDetail,
    AgentRunReason,
    AgentRunTaskEvent,
    StartTaskRequest,
    StartTaskResponse,
    TaskListResponse,
    TaskState,
)
from fred_core.tasks.service import TaskNotAcknowledgeableError, TaskService
from fred_core.tasks.sse import task_event_stream, with_heartbeat
from fred_core.tasks.store import TaskAlreadyExistsError, TaskNotFoundError
from pydantic import BaseModel

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.models.agent_run_task_models import AgentRunScheduleRow
from control_plane_backend.product.agent_run_store import AGENT_RUN_LIFECYCLE_LOCK
from control_plane_backend.product.agent_run_task_store import AgentRunTaskStore
from control_plane_backend.product.dependencies import (
    build_product_service_dependencies,
)
from control_plane_backend.product.schemas import (
    AgentRunScheduleSummary,
    CreateAgentRunScheduleRequest,
    StartAgentRunTaskRequest,
)
from control_plane_backend.product.service import get_runtime_binding_for_team
from control_plane_backend.teams.service import require_team_access


class _AgentRunStart(BaseModel):
    kind: Literal["agent_run"] = "agent_run"


class AgentRunEventReport(BaseModel):
    state: TaskState
    seq: int = 0
    reason: AgentRunReason | None = None


class _StoredScheduleTemplate(BaseModel):
    person_id: str
    roles: tuple[str, ...]
    team_id: str
    runtime_id: str
    runtime_client_id: str
    runtime_subject: str
    task_queue: str
    agent_instance_id: str
    agent_id: str
    prompt: str
    scope: AgentRunScope
    budget: AgentRunBudget
    schedule: Schedule


def _get_task_service(request: Request) -> TaskService:
    container = get_application_container(request)
    return container.get_task_service()


def _get_rebac_engine(request: Request) -> RebacEngine:
    container = get_application_container(request)
    return container.get_rebac_engine()


def _get_agent_run_task_store(request: Request) -> AgentRunTaskStore:
    return get_application_container(request).get_agent_run_task_store()


def build_tasks_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["tasks"])

    @router.post(
        "/teams/{team_id}/agent-instances/{agent_instance_id}/tasks",
        status_code=202,
        response_model=StartTaskResponse,
        operation_id="start_agent_run_task",
    )
    async def start_agent_run_task(
        team_id: TeamId,
        agent_instance_id: str,
        body: StartAgentRunTaskRequest,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
    ) -> StartTaskResponse:
        container = get_application_container(request)
        deps = build_product_service_dependencies(container)
        team_id = await require_team_access(
            user,
            team_id,
            deps.team_dependencies,
            [TeamPermission.CAN_USE_TEAM_AGENTS],
        )
        instance = await deps.get_agent_instance_store().get_for_team(
            agent_instance_id, team_id
        )
        if instance is None or not instance.enabled:
            raise HTTPException(status_code=404, detail="agent_instance_not_available")
        source = next(
            (
                item
                for item in deps.configuration.platform.runtime_catalog_sources
                if item.enabled and item.runtime_id == instance.source_runtime_id
            ),
            None,
        )
        if (
            source is None
            or source.workload_client_id is None
            or source.workload_subject is None
            or source.agent_task_queue is None
        ):
            raise HTTPException(status_code=503, detail="agent_runtime_not_configured")
        binding = await get_runtime_binding_for_team(agent_instance_id, team_id, deps)
        if binding is None:
            raise HTTPException(status_code=404, detail="agent_instance_not_available")
        task_id = str(uuid4())
        workflow_id = f"agent-run-{task_id}"
        run_id = str(uuid4())
        record = AgentRunAdmissionRecord(
            person_id=user.uid,
            roles=tuple(user.roles),
            team_id=str(team_id),
            runtime_id=source.runtime_id,
            agent_instance_id=agent_instance_id,
            agent_id=binding.template_agent_id,
            prompt=body.prompt,
            scope=body.scope,
            created_by=user.uid,
            created_at=datetime.now(UTC),
            run_id=run_id,
            budget=AgentRunBudget(
                wall_clock_seconds=(
                    binding.tuning.run_ceiling_seconds
                    or deps.configuration.app.agent_run_default_ceiling_seconds
                ),
                max_concurrent_children=(
                    deps.configuration.app.agent_run_max_concurrent_children
                ),
            ),
        )
        admission_store = container.get_agent_run_task_store()
        async with container.get_team_metadata_store().advisory_lock(
            AGENT_RUN_LIFECYCLE_LOCK
        ) as session:
            await deps.team_dependencies.rebac.require_user_standing(user.uid)
            await service.start(
                cast(Any, _AgentRunStart()),
                created_by=user.uid,
                team_id=str(team_id),
                task_id=task_id,
                session=session,
            )
            await admission_store.create(
                task_id=task_id,
                workflow_id=workflow_id,
                runtime_client_id=source.workload_client_id,
                runtime_subject=source.workload_subject,
                record=record,
                session=session,
            )
        try:
            client = await container.get_temporal_client_provider().get_client()
            await client.start_workflow(
                "fred.agent_run.v1",
                AgentRunWorkflowInputV1(
                    task_id=task_id, workflow_id=workflow_id, record=record
                ),
                id=workflow_id,
                task_queue=source.agent_task_queue,
            )
        except asyncio.CancelledError:
            await service.bind_execution(task_id, execution_id=workflow_id)
            await service.fail_task(task_id, "Agent run scheduling was cancelled")
            raise
        except Exception as exc:
            await service.bind_execution(task_id, execution_id=workflow_id)
            await service.fail_task(task_id, "Agent run could not be scheduled")
            raise HTTPException(
                status_code=503, detail="agent_run_dispatch_failed"
            ) from exc
        await service.bind_execution(task_id, execution_id=workflow_id)
        return StartTaskResponse(task_id=task_id)

    @router.post(
        "/teams/{team_id}/agent-instances/{agent_instance_id}/task-schedules",
        status_code=201,
        response_model=AgentRunScheduleSummary,
        operation_id="create_agent_run_schedule",
    )
    async def create_agent_run_schedule(
        team_id: TeamId,
        agent_instance_id: str,
        body: CreateAgentRunScheduleRequest,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
    ) -> AgentRunScheduleSummary:
        container = get_application_container(request)
        deps = build_product_service_dependencies(container)
        team_id = await require_team_access(
            user,
            team_id,
            deps.team_dependencies,
            [TeamPermission.CAN_USE_TEAM_AGENTS],
        )
        instance = await deps.get_agent_instance_store().get_for_team(
            agent_instance_id, team_id
        )
        if instance is None or not instance.enabled:
            raise HTTPException(status_code=404, detail="agent_instance_not_available")
        source = next(
            (
                item
                for item in deps.configuration.platform.runtime_catalog_sources
                if item.enabled and item.runtime_id == instance.source_runtime_id
            ),
            None,
        )
        if (
            source is None
            or source.workload_client_id is None
            or source.workload_subject is None
            or source.agent_task_queue is None
        ):
            raise HTTPException(status_code=503, detail="agent_runtime_not_configured")
        binding = await get_runtime_binding_for_team(agent_instance_id, team_id, deps)
        if binding is None:
            raise HTTPException(status_code=404, detail="agent_instance_not_available")
        schedule_id = str(uuid4())
        created_at = datetime.now(UTC)
        template = _StoredScheduleTemplate(
            person_id=user.uid,
            roles=tuple(user.roles),
            team_id=str(team_id),
            runtime_id=source.runtime_id,
            runtime_client_id=source.workload_client_id,
            runtime_subject=source.workload_subject,
            task_queue=source.agent_task_queue,
            agent_instance_id=agent_instance_id,
            agent_id=binding.template_agent_id,
            prompt=body.prompt,
            scope=body.scope,
            budget=AgentRunBudget(
                wall_clock_seconds=(
                    binding.tuning.run_ceiling_seconds
                    or deps.configuration.app.agent_run_default_ceiling_seconds
                ),
                max_concurrent_children=(
                    deps.configuration.app.agent_run_max_concurrent_children
                ),
            ),
            schedule=body.schedule,
        )
        row = AgentRunScheduleRow(
            schedule_id=schedule_id,
            team_id=str(team_id),
            agent_instance_id=agent_instance_id,
            runtime_id=source.runtime_id,
            created_by=user.uid,
            template_json=template.model_dump_json(),
            created_at=created_at,
        )
        async with container.get_team_metadata_store().advisory_lock(
            AGENT_RUN_LIFECYCLE_LOCK
        ) as session:
            # The account-delete path holds the same lock. Rechecking inside it
            # prevents a schedule admitted just before revocation from being
            # created after that person's purge has completed.
            await deps.team_dependencies.rebac.require_user_standing(user.uid)
            await container.get_agent_run_task_store().create_schedule(
                row, session=session
            )
            try:
                client = await container.get_temporal_client_provider().get_client()
                await ensure_schedule(
                    client,
                    schedule_id,
                    workflow="fred.scheduled_agent_run.v1",
                    workflow_id=f"agent-run-schedule-{schedule_id}",
                    task_queue=source.agent_task_queue,
                    spec=to_temporal_spec(body.schedule, spread_over=schedule_id),
                    args=(
                        ScheduledAgentRunInputV1(
                            schedule_id=schedule_id, runtime_id=source.runtime_id
                        ),
                    ),
                )
            except asyncio.CancelledError:
                await container.get_agent_run_task_store().delete_schedule(
                    schedule_id, session=session
                )
                raise
            except Exception as exc:
                await container.get_agent_run_task_store().delete_schedule(
                    schedule_id, session=session
                )
                raise HTTPException(
                    status_code=503, detail="agent_schedule_dispatch_failed"
                ) from exc
        return AgentRunScheduleSummary(
            schedule_id=schedule_id,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            schedule=body.schedule,
            created_by=user.uid,
            created_at=created_at,
        )

    @router.get(
        "/teams/{team_id}/agent-instances/{agent_instance_id}/task-schedules",
        response_model=list[AgentRunScheduleSummary],
        operation_id="list_agent_run_schedules",
    )
    async def list_agent_run_schedules(
        team_id: TeamId,
        agent_instance_id: str,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
    ) -> list[AgentRunScheduleSummary]:
        container = get_application_container(request)
        deps = build_product_service_dependencies(container)
        await require_team_access(user, team_id, deps.team_dependencies)
        rows = await container.get_agent_run_task_store().list_schedules(str(team_id))
        is_admin = await deps.team_dependencies.rebac.has_permission(
            RebacReference(Resource.USER, user.uid),
            TeamPermission.CAN_ADMINISTER_MEMBERS,
            RebacReference(Resource.TEAM, str(team_id)),
        )
        return [
            AgentRunScheduleSummary(
                schedule_id=row.schedule_id,
                team_id=TeamId(row.team_id),
                agent_instance_id=row.agent_instance_id,
                schedule=_StoredScheduleTemplate.model_validate_json(
                    row.template_json
                ).schedule,
                created_by=row.created_by,
                created_at=row.created_at,
            )
            for row in rows
            if row.agent_instance_id == agent_instance_id
            and (row.created_by == user.uid or is_admin)
        ]

    @router.delete(
        "/teams/{team_id}/agent-instances/{agent_instance_id}/task-schedules/{schedule_id}",
        status_code=204,
        operation_id="delete_agent_run_schedule",
    )
    async def delete_agent_run_schedule(
        team_id: TeamId,
        agent_instance_id: str,
        schedule_id: str,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
    ) -> None:
        container = get_application_container(request)
        deps = build_product_service_dependencies(container)
        await require_team_access(user, team_id, deps.team_dependencies)
        row = await container.get_agent_run_task_store().get_schedule(schedule_id)
        is_admin = await deps.team_dependencies.rebac.has_permission(
            RebacReference(Resource.USER, user.uid),
            TeamPermission.CAN_ADMINISTER_MEMBERS,
            RebacReference(Resource.TEAM, str(team_id)),
        )
        if (
            row is None
            or row.team_id != str(team_id)
            or row.agent_instance_id != agent_instance_id
            or (row.created_by != user.uid and not is_admin)
        ):
            raise HTTPException(status_code=404, detail="agent_run_schedule_not_found")
        client = await container.get_temporal_client_provider().get_client()
        await delete_schedule_if_exists(client, schedule_id)
        await container.get_agent_run_task_store().delete_schedule(schedule_id)

    @router.post(
        "/internal/agent-run-tasks/{task_id}/events",
        status_code=204,
        operation_id="record_agent_run_task_event",
    )
    async def record_agent_run_task_event(
        task_id: str,
        body: AgentRunEventReport,
        caller: Annotated[KeycloakUser, Depends(get_authenticated_caller)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        store: Annotated[AgentRunTaskStore, Depends(_get_agent_run_task_store)],
    ) -> None:
        require_workload_caller(caller)
        admission = await store.get(task_id)
        run = await service.get_run(task_id)
        if admission is None or run is None:
            raise HTTPException(status_code=404, detail="agent_run_task_not_found")
        if (
            caller.client_id != admission.runtime_client_id
            or caller.uid != admission.runtime_subject
        ):
            raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
        current_state = TaskState(run.state)
        if current_state.is_terminal:
            current_reason = (
                run.detail.get("reason") if isinstance(run.detail, dict) else None
            )
            if current_state == body.state and current_reason == body.reason:
                return
            raise HTTPException(
                status_code=409, detail="agent_run_task_terminal_conflict"
            )
        await service.record(
            AgentRunTaskEvent(
                task_id=task_id,
                state=body.state,
                seq=body.seq,
                timestamp=datetime.now(UTC),
                detail=AgentRunDetail(reason=body.reason),
            )
        )

    @router.post(
        "/internal/agent-run-schedules/{schedule_id}/occurrences",
        response_model=ScheduledAgentRunOccurrence,
        operation_id="create_agent_run_schedule_occurrence",
    )
    async def create_agent_run_schedule_occurrence(
        schedule_id: str,
        body: ScheduledAgentRunOccurrenceRequest,
        request: Request,
        caller: Annotated[KeycloakUser, Depends(get_authenticated_caller)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        store: Annotated[AgentRunTaskStore, Depends(_get_agent_run_task_store)],
    ) -> ScheduledAgentRunOccurrence:
        require_workload_caller(caller)
        row = await store.get_schedule(schedule_id)
        if row is None:
            raise HTTPException(status_code=404, detail="agent_run_schedule_not_found")
        template = _StoredScheduleTemplate.model_validate_json(row.template_json)
        if (
            caller.client_id != template.runtime_client_id
            or caller.uid != template.runtime_subject
        ):
            raise HTTPException(status_code=403, detail="workload_caller_not_allowed")
        container = get_application_container(request)
        deps = build_product_service_dependencies(container)
        instance = await deps.get_agent_instance_store().get_for_team(
            template.agent_instance_id, TeamId(template.team_id)
        )
        source = next(
            (
                item
                for item in deps.configuration.platform.runtime_catalog_sources
                if item.enabled and item.runtime_id == template.runtime_id
            ),
            None,
        )
        if (
            instance is None
            or not instance.enabled
            or instance.source_runtime_id != template.runtime_id
            or instance.source_agent_id != template.agent_id
            or source is None
            or source.workload_client_id != template.runtime_client_id
            or source.workload_subject != template.runtime_subject
            or source.agent_task_queue != template.task_queue
        ):
            raise HTTPException(
                status_code=409, detail="agent_run_schedule_binding_changed"
            )
        subject = KeycloakUser(
            uid=template.person_id,
            username=template.person_id,
            roles=list(template.roles),
        )
        await require_team_access(
            subject,
            TeamId(template.team_id),
            deps.team_dependencies,
            [TeamPermission.CAN_USE_TEAM_AGENTS],
        )
        occurrence_key = str(
            uuid5(
                NAMESPACE_URL,
                f"fred:agent-run-occurrence:{schedule_id}:{body.workflow_id}:{body.run_id}",
            )
        )
        async with store.lock_occurrence(occurrence_key) as session:
            existing = await store.get_by_occurrence(occurrence_key, session=session)
            if existing is not None:
                record = AgentRunAdmissionRecord.model_validate_json(
                    existing.payload_json
                )
                run = await service.get_run(existing.task_id, session=session)
                if run is None:
                    raise HTTPException(
                        status_code=404, detail="agent_run_task_not_found"
                    )
                if run.execution_id not in (None, body.workflow_id):
                    raise HTTPException(
                        status_code=409, detail="schedule_occurrence_conflict"
                    )
                if not TaskState(run.state).is_terminal and run.execution_id is None:
                    await service.bind_execution(
                        existing.task_id,
                        execution_id=body.workflow_id,
                        session=session,
                    )
                return ScheduledAgentRunOccurrence(
                    task_id=existing.task_id,
                    workflow_id=existing.workflow_id,
                    record=record,
                )
            task_id = str(uuid5(NAMESPACE_URL, f"fred:agent-run-task:{occurrence_key}"))
            child_workflow_id = str(
                uuid5(NAMESPACE_URL, f"fred:agent-run-execution:{occurrence_key}")
            )
            record = AgentRunAdmissionRecord(
                person_id=template.person_id,
                roles=template.roles,
                team_id=template.team_id,
                runtime_id=template.runtime_id,
                agent_instance_id=template.agent_instance_id,
                agent_id=template.agent_id,
                prompt=template.prompt,
                scope=template.scope,
                created_by=template.person_id,
                created_at=datetime.now(UTC),
                run_id=body.run_id,
                budget=template.budget,
            )
            async with container.get_team_metadata_store().advisory_lock(
                AGENT_RUN_LIFECYCLE_LOCK, session=session
            ):
                await deps.team_dependencies.rebac.require_user_standing(
                    template.person_id
                )
                try:
                    await service.start(
                        cast(Any, _AgentRunStart()),
                        created_by=template.person_id,
                        team_id=template.team_id,
                        task_id=task_id,
                        session=session,
                    )
                except TaskAlreadyExistsError:
                    if not await store.is_matching_task(
                        task_id=task_id,
                        person_id=template.person_id,
                        team_id=template.team_id,
                        session=session,
                    ):
                        raise HTTPException(
                            status_code=409, detail="schedule_occurrence_conflict"
                        )
                await store.create(
                    task_id=task_id,
                    workflow_id=child_workflow_id,
                    occurrence_key=occurrence_key,
                    runtime_client_id=template.runtime_client_id,
                    runtime_subject=template.runtime_subject,
                    record=record,
                    session=session,
                )
                await service.bind_execution(
                    task_id, execution_id=body.workflow_id, session=session
                )
            return ScheduledAgentRunOccurrence(
                task_id=task_id, workflow_id=child_workflow_id, record=record
            )

    @router.post("/tasks", status_code=202, response_model=StartTaskResponse)
    async def start_task(
        body: StartTaskRequest,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> StartTaskResponse:
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )
        return await service.start(body, created_by=user.uid)

    @router.get("/tasks", response_model=TaskListResponse)
    async def list_tasks(
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
        scope: str = Query(default="platform", pattern="^(platform|team|user)$"),
        team_id: str | None = Query(default=None),
        kind: str | None = Query(default=None),
        state: str | None = Query(default=None),
    ) -> TaskListResponse:
        return await list_tasks_scoped(
            service, rebac, user, scope=scope, team_id=team_id, kind=kind, state=state
        )

    @router.get("/tasks/{task_id}/events")
    async def stream_task_events(
        task_id: str,
        request: Request,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> StreamingResponse:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await authorize_task_stream(user, run, rebac)

        last_event_id = request.headers.get("Last-Event-ID")
        try:
            after_seq = int(last_event_id) if last_event_id else -1
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be a non-negative integer"
            )

        return StreamingResponse(
            with_heartbeat(
                task_event_stream(
                    service,
                    task_id,
                    after_seq=after_seq,
                    is_disconnected=request.is_disconnected,
                )
            ),
            media_type="text/event-stream",
        )

    @router.post("/tasks/{task_id}/cancel", status_code=202)
    async def cancel_task(
        task_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> dict:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await authorize_task_mutation(user, run, rebac)
        await service.cancel(task_id)
        return {"task_id": task_id}

    @router.post("/tasks/{task_id}/ack", response_model=AcknowledgeTaskResponse)
    async def acknowledge_task(
        task_id: str,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        service: Annotated[TaskService, Depends(_get_task_service)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
    ) -> AcknowledgeTaskResponse:
        run = await service.get_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Task not found")
        # View-level rule (§2.10) — deliberately NOT authorize_task_mutation:
        # any team reader may dismiss a teammate's failed task, not only its
        # creator or a platform admin.
        await authorize_task_access(user, run, rebac)
        try:
            return await service.acknowledge(task_id, by=user.uid)
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="Task not found")
        except TaskNotAcknowledgeableError:
            raise HTTPException(
                status_code=409, detail="Task does not currently need attention"
            )

    return router
