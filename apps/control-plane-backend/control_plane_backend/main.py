from __future__ import annotations

import contextlib
import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fred_core import (
    KeycloakUser,
    get_config,
    get_current_user,
    initialize_user_security,
    log_setup,
    require_admin,
)
from fred_core.common import read_env_bool
from fred_core.kpi import KPIMiddleware
from fred_core.logs.null_log_store import NullLogStore
from fred_core.scheduler import SchedulerBackend
from pydantic import BaseModel

from control_plane_backend.app.container import (
    build_application_container,
    initialize_shared_stores,
)
from control_plane_backend.app.dependencies import (
    attach_application_container,
    get_application_configuration,
)
from control_plane_backend.config.loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from control_plane_backend.config.models import AppState
from control_plane_backend.product.api import router as product_router
from control_plane_backend.scheduler.dependencies import (
    build_lifecycle_action_dependencies,
)
from control_plane_backend.scheduler.memory import run_lifecycle_manager_once_in_memory
from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_models import (
    PolicyEvaluationResult,
    PolicyResolutionRequest,
)
from control_plane_backend.scheduler.temporal.structures import (
    LifecycleManagerInput,
    LifecycleManagerResult,
)
from control_plane_backend.kpi.api import build_kpi_router
from control_plane_backend.tasks.api import build_tasks_router
from control_plane_backend.teams.api import (
    register_exception_handlers as register_team_exception_handlers,
)
from control_plane_backend.teams.api import router as teams_router
from control_plane_backend.users.api import (
    register_exception_handlers as register_user_exception_handlers,
)
from control_plane_backend.users.api import router as users_router

logger = logging.getLogger(__name__)


class PolicySummaryResponse(PolicyEvaluationResult):
    default_rule_count: int
    catalog_path: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["control-plane"] = "control-plane"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    service: Literal["control-plane"] = "control-plane"
    scheduler_enabled: bool
    loaded_config_file: str | None = None
    loaded_env_file: str | None = None


class WorkflowStartResponse(BaseModel):
    status: Literal["queued", "completed"] = "queued"
    backend: SchedulerBackend
    workflow_id: str | None = None
    run_id: str | None = None
    result: LifecycleManagerResult | None = None


def _norm_origin(origin: object) -> str:
    return str(origin).rstrip("/")


def create_app() -> FastAPI:
    configuration = load_configuration()
    env_file = get_loaded_env_file_path() or "<unset>"
    config_file = get_loaded_config_file_path() or "<unset>"
    log_setup(
        service_name="control-plane",
        log_level=configuration.app.log_level,
        store=NullLogStore(),
    )
    logger.info("Environment file: %s | Configuration file: %s", env_file, config_file)

    docs_enabled = read_env_bool("PRODUCTION_FASTAPI_DOCS_ENABLED", default=True)
    container = build_application_container(configuration)
    initialize_shared_stores(container)
    container.start_metrics_exporter()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            await container.shutdown()
            logger.info("[MAIN] Lifespan exit: orderly shutdown.")

    app = FastAPI(
        docs_url=f"{configuration.app.base_url}/docs" if docs_enabled else None,
        redoc_url=f"{configuration.app.base_url}/redoc" if docs_enabled else None,
        openapi_url=f"{configuration.app.base_url}/openapi.json"
        if docs_enabled
        else None,
        lifespan=lifespan,
    )
    attach_application_container(app, container)
    initialize_user_security(configuration.security.user)
    allowed_origins = list(
        {_norm_origin(origin) for origin in configuration.security.authorized_origins}
    )
    logger.info("[CORS] allow_origins=%s", allowed_origins)

    app.dependency_overrides[get_config] = get_application_configuration

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(KPIMiddleware, kpi=container.get_kpi_writer)

    router = APIRouter(prefix=configuration.app.base_url)

    @router.get("/healthz", summary="Liveness probe", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse()

    @router.get("/ready", summary="Readiness probe", response_model=ReadyResponse)
    async def ready() -> ReadyResponse:
        state = AppState(
            loaded_config_file=get_loaded_config_file_path(),
            loaded_env_file=get_loaded_env_file_path(),
        )
        return ReadyResponse(
            scheduler_enabled=configuration.scheduler.enabled,
            loaded_config_file=state.loaded_config_file,
            loaded_env_file=state.loaded_env_file,
        )

    @router.get("/policies/purge", response_model=PolicySummaryResponse)
    async def get_purge_policy_summary(
        user: KeycloakUser = Depends(get_current_user),
    ) -> PolicySummaryResponse:
        require_admin(user)
        catalog = container.get_policy_catalog()
        policy = catalog.conversation_policies.purge
        resolved = evaluate_policy_for_request(PolicyResolutionRequest(), catalog)
        return PolicySummaryResponse(
            **resolved.model_dump(),
            default_rule_count=len(policy.rules),
            catalog_path=str(container.get_policy_catalog_path()),
        )

    @router.post("/policies/purge/resolve", response_model=PolicyEvaluationResult)
    async def resolve_purge(
        request: PolicyResolutionRequest,
        user: KeycloakUser = Depends(get_current_user),
    ) -> PolicyEvaluationResult:
        require_admin(user)
        catalog = container.get_policy_catalog()
        return evaluate_policy_for_request(request, catalog)

    @router.post(
        "/lifecycle/run-once",
        summary="Trigger one LifecycleManager workflow",
        response_model=WorkflowStartResponse,
    )
    async def trigger_lifecycle_run_once(
        payload: LifecycleManagerInput,
        user: KeycloakUser = Depends(get_current_user),
    ) -> WorkflowStartResponse:
        require_admin(user)
        if not configuration.scheduler.enabled:
            raise HTTPException(
                status_code=400,
                detail="Scheduler is disabled. Enable configuration.scheduler.enabled.",
            )

        backend = container.get_scheduler_backend()
        if backend == SchedulerBackend.MEMORY:
            result = await run_lifecycle_manager_once_in_memory(
                payload,
                deps=build_lifecycle_action_dependencies(container),
            )
            return WorkflowStartResponse(
                status="completed",
                backend=SchedulerBackend.MEMORY,
                result=result,
            )

        provider = container.get_temporal_client_provider()
        client = await provider.get_client()
        workflow_id = (
            f"{configuration.scheduler.temporal.workflow_id_prefix}-manual-{uuid4()}"
        )
        handle = await client.start_workflow(
            "LifecycleManagerWorkflow",
            payload,
            id=workflow_id,
            task_queue=configuration.scheduler.temporal.task_queue,
        )
        if handle.run_id is None:
            raise HTTPException(
                status_code=500,
                detail="Temporal returned no run_id for started workflow.",
            )
        return WorkflowStartResponse(
            status="queued",
            backend=SchedulerBackend.TEMPORAL,
            workflow_id=handle.id,
            run_id=handle.run_id,
        )

    router.include_router(users_router)
    router.include_router(teams_router)
    router.include_router(product_router)
    router.include_router(build_tasks_router())
    router.include_router(build_kpi_router())

    register_user_exception_handlers(app)
    register_team_exception_handlers(app)
    app.include_router(router)
    return app
