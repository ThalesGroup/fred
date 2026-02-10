# Copyright Thales 2025
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

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entrypoint for the Agentic Backend App.
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import initialize_user_security, log_setup, register_exception_handlers
from fred_core.kpi import emit_process_kpis
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator

from agentic_backend.application_context import (
    ApplicationContext,
    get_agent_store,
    get_session_store,
)
from agentic_backend.common.config_loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents import agent_controller
from agentic_backend.core.agents.agent_factory import AgentFactory
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.chatbot import chatbot_controller
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.feedback import feedback_controller
from agentic_backend.core.logs import logs_controller
from agentic_backend.core.mcp import mcp_controller
from agentic_backend.core.monitoring import monitoring_controller
from agentic_backend.scheduler.scheduler_controller import AgentTasksController

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logger = logging.getLogger(__name__)


def _norm_origin(o) -> str:
    # Ensure exact match with browser's Origin header (no trailing slash)
    return str(o).rstrip("/")


# -----------------------
# APP CREATION
# -----------------------


def create_app() -> FastAPI:
    configuration: Configuration = load_configuration()
    env_file = get_loaded_env_file_path() or "<unset>"
    config_file = get_loaded_config_file_path() or "<unset>"

    base_url = configuration.app.base_url

    application_context = ApplicationContext(configuration)
    log_setup(
        service_name="agentic",
        log_level=configuration.app.log_level,
        store=application_context.get_log_store(),
    )
    logger.info(f"[MAIN] create_app() called with .env={env_file} config={config_file}")
    application_context._log_config_summary()

    # The correct and final code to use
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Fred lifespan: manages the lifecycle of the application's core services.
        - Startup instantiates and launches background tasks.
        - `yield` hands control to the server.
        - `finally` gracefully shuts down all tasks and services.
        """
        logger.info("[MAIN] Lifespan enter.")

        # Instantiate dependencies *within* the lifespan context
        app.state.configuration = configuration
        mcp_manager = await application_context.get_mcp_server_manager()
        agent_loader = AgentLoader(configuration, get_agent_store())
        agent_manager = AgentManager(configuration, agent_loader, get_agent_store())
        agent_factory = AgentFactory(
            configuration=configuration,
            manager=agent_manager,
            loader=agent_loader,
        )
        session_orchestrator = SessionOrchestrator(
            configuration=configuration,
            session_store=get_session_store(),
            attachments_store=application_context.get_session_attachment_store(),
            agent_factory=agent_factory,
            agent_manager=agent_manager,
            history_store=application_context.get_history_store(),
            kpi=application_context.get_kpi_writer(),
        )
        process_kpi_task = None
        kpi_interval_env = configuration.app.kpi_process_metrics_interval_sec
        if kpi_interval_env:
            try:
                interval_s = float(kpi_interval_env)
            except ValueError:
                logger.error(
                    "Invalid KPI process metrics interval: %s. Disabling KPI process metrics task.",
                    kpi_interval_env,
                )
                interval_s = 0
            if interval_s > 0:
                process_kpi_task = asyncio.create_task(
                    emit_process_kpis(interval_s, application_context.get_kpi_writer())
                )
        try:
            await agent_manager.bootstrap()
        except Exception:
            logger.critical(
                "❌ AgentManager bootstrap FAILED! Application cannot proceed.",
                exc_info=True,
            )
            # Fail fast: prevent server from starting in a broken state.
            raise

        # Store state on app.state for access via dependency injection
        app.state.mcp_manager = mcp_manager
        app.state.agent_manager = agent_manager
        app.state.session_orchestrator = session_orchestrator

        try:
            yield  # Hand control to the FastAPI server, but keep the startup task running
        finally:
            if process_kpi_task:
                process_kpi_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await process_kpi_task
            await application_context.shutdown()
            logger.info("[MAIN] Lifespan exit: orderly shutdown.")
            logger.info("[] Shutdown complete.")

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
        lifespan=lifespan,
    )

    if configuration.app.metrics_enabled:
        Instrumentator().instrument(app)
        start_http_server(
            configuration.app.metrics_port,
            addr=configuration.app.metrics_address,
        )

    # Register exception handlers
    register_exception_handlers(app)
    agent_controller.register_exception_handlers(app)

    allowed_origins = list(
        {_norm_origin(o) for o in configuration.security.authorized_origins}
    )
    logger.info("[MAIN][CORS] allow_origins=%s", allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    initialize_user_security(configuration.security.user)

    router = APIRouter(prefix=base_url)
    router.include_router(agent_controller.router)
    router.include_router(mcp_controller.router)
    router.include_router(chatbot_controller.router)
    router.include_router(monitoring_controller.router)
    router.include_router(feedback_controller.router)
    router.include_router(logs_controller.router)
    if configuration.scheduler.enabled:
        logger.info("[MAIN] Activating temporal scheduler.")
        task_queue = configuration.scheduler.temporal.task_queue
        temporal_client_provider = application_context.get_temporal_client_provider()
        AgentTasksController(router, temporal_client_provider, task_queue)

    app.include_router(router)
    logger.info("[MAIN] All controllers registered.")
    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn app.main:create_app --factory ...")
