from __future__ import annotations

import contextlib
import logging
from typing import Literal

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import get_config, initialize_user_security, log_setup
from fred_core.users.store.postgres_user_store import init_user_store
from fred_core.common import read_env_bool
from fred_core.logs.null_log_store import NullLogStore
from pydantic import BaseModel
from fred_core.sql import create_async_engine_from_config

from fred_evaluation_backend.campaigns.api import build_evaluations_router
from fred_evaluation_backend.config.loader import load_configuration
from fred_evaluation_backend.execution.control_plane_client import ControlPlaneClient

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["fred-evaluation"] = "fred-evaluation"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    service: Literal["fred-evaluation"] = "fred-evaluation"


def create_app() -> FastAPI:
    configuration = load_configuration()
    log_setup(
        service_name="fred-evaluation",
        log_level=configuration.app.log_level,
        store=NullLogStore(),
    )

    initialize_user_security(configuration.security.user)
    docs_enabled = read_env_bool("PRODUCTION_FASTAPI_DOCS_ENABLED", default=True)
    engine = create_async_engine_from_config(configuration.database)
    init_user_store(engine)

    import os
    cp_token = os.environ.get(configuration.control_plane.credential_ref)
    control_plane_client = ControlPlaneClient(
        base_url=configuration.control_plane.base_url,
        service_token=cp_token,
        runtime_base_url=configuration.control_plane.runtime_base_url,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db_engine = engine
        app.state.control_plane_client = control_plane_client
        yield
        await engine.dispose()

    app = FastAPI(
        docs_url=f"{configuration.app.base_url}/docs" if docs_enabled else None,
        redoc_url=f"{configuration.app.base_url}/redoc" if docs_enabled else None,
        openapi_url=f"{configuration.app.base_url}/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    allowed_origins = list(configuration.security.authorized_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    router = APIRouter(prefix=configuration.app.base_url)

    @router.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse()

    @router.get("/ready", response_model=ReadyResponse)
    async def ready() -> ReadyResponse:
        return ReadyResponse()

    app.dependency_overrides[get_config] = lambda: configuration

    router.include_router(build_evaluations_router())
    app.include_router(router)
    return app