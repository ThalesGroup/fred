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

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import initialize_user_security, log_setup, register_exception_handlers

from agentic_backend.application_context import (
    ApplicationContext,
    get_agent_store,
    get_session_store,
)
from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration
from agentic_backend.core import logs_controller
from agentic_backend.core.agents import agent_controller
from agentic_backend.core.agents.agent_factory import AgentFactory
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.chatbot import chatbot_controller
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.feedback import feedback_controller
from agentic_backend.core.monitoring import monitoring_controller

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logger = logging.getLogger(__name__)


def _norm_origin(o) -> str:
    # Ensure exact match with browser's Origin header (no trailing slash)
    return str(o).rstrip("/")


def load_environment(dotenv_path: str = "./config/.env"):
    if load_dotenv(dotenv_path):
        logging.getLogger().info(f"✅ Loaded environment variables from: {dotenv_path}")
    else:
        logging.getLogger().warning(f"⚠️ No .env file found at: {dotenv_path}")


# -----------------------
# APP CREATION
# -----------------------


def create_app() -> FastAPI:
    load_environment()
    config_file = os.environ["CONFIG_FILE"]
    configuration: Configuration = parse_server_configuration(config_file)
    base_url = configuration.app.base_url

    application_context = ApplicationContext(configuration)
    log_setup(
        service_name="agentic",
        log_level=configuration.app.log_level,
        store=application_context.get_log_store(),
    )
    logger.info(f"🛠️ create_app() called with base_url={base_url}")

    # The correct and final code to use
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Fred lifespan: manages the lifecycle of the application's core services.
        - Startup instantiates and launches background tasks.
        - `yield` hands control to the server.
        - `finally` gracefully shuts down all tasks and services.
        """
        logger.info("🚀 Lifespan enter.")

        # Instantiate dependencies *within* the lifespan context
        app.state.configuration = configuration
        agent_loader = AgentLoader(configuration, get_agent_store())
        agent_manager = AgentManager(configuration, agent_loader, get_agent_store())
        agent_factory = AgentFactory(agent_manager, agent_loader)
        session_orchestrator = SessionOrchestrator(
            get_session_store(),
            agent_manager=agent_manager,
            agent_factory=agent_factory,
        )
        try:
            await agent_manager.bootstrap()
        except Exception:
            logger.critical(
                "❌ AgentManager bootstrap FAILED! Application cannot proceed.",
                exc_info=True,
            )
            # Depending on severity, you might re-raise the exception or use sys.exit()
            # to prevent the server from starting in a broken state.

        # Store state on app.state for access via dependency injection
        app.state.agent_manager = agent_manager
        app.state.session_orchestrator = session_orchestrator

        try:
            yield  # Hand control to the FastAPI server, but keep the startup task running
        finally:
            logger.info("🧹 Lifespan exit: orderly shutdown.")
            logger.info("✅ Shutdown complete.")

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
        lifespan=lifespan,
    )

    # Register exception handlers
    register_exception_handlers(app)
    allowed_origins = list(
        {_norm_origin(o) for o in configuration.security.authorized_origins}
    )
    logger.info("[CORS] allow_origins=%s", allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    initialize_user_security(configuration.security.user)

    router = APIRouter(prefix=base_url)
    router.include_router(agent_controller.router)
    router.include_router(chatbot_controller.router)
    router.include_router(monitoring_controller.router)
    router.include_router(feedback_controller.router)
    router.include_router(logs_controller.router)
    app.include_router(router)
    logger.info("🧩 All controllers registered.")
    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn app.main:create_app --factory ...")
