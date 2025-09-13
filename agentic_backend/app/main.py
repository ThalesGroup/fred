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
from contextlib import asynccontextmanager
import logging
import os


from app.core.agents import agent_controller
from app.core.agents.agent_manager import AgentManager
from app.core.chatbot import chatbot_controller
from app.core.chatbot.session_orchestrator import SessionOrchestrator
from app.core.feedback import feedback_controller
from app.application_context import (
    ApplicationContext,
    get_agent_store,
    get_session_store,
)
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.core.monitoring import monitoring_controller
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import initialize_user_security, register_exception_handlers
from rich.logging import RichHandler


# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logger = logging.getLogger(__name__)


def _norm_origin(o) -> str:
    # Ensure exact match with browser's Origin header (no trailing slash)
    return str(o).rstrip("/")


def configure_logging(log_level: str):
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=False, show_time=False, show_path=False)],
    )
    logging.getLogger(__name__).info(
        f"Logging configured at {log_level.upper()} level."
    )


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
    configure_logging(configuration.app.log_level)
    base_url = configuration.app.base_url
    logger.info(f"🛠️ create_app() called with base_url={base_url}")

    ApplicationContext(configuration)

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
        agent_manager = AgentManager(configuration, get_agent_store())
        session_orchestrator = SessionOrchestrator(get_session_store(), agent_manager)

        # Store state on app.state for access via dependency injection
        app.state.agent_manager = agent_manager
        app.state.session_orchestrator = session_orchestrator

        # Use asyncio to launch a background task that runs for the duration of the app's life.
        # We remove the separate TaskGroup to prevent the race condition.
        startup_task = asyncio.create_task(agent_manager.initialize_and_start_retries())

        try:
            yield  # Hand control to the FastAPI server, but keep the startup task running
        finally:
            logger.info("🧹 Lifespan exit: orderly shutdown.")
            # Cancel the background task and wait for it to finish
            startup_task.cancel()
            try:
                await startup_task
            except asyncio.CancelledError:
                pass  # Expected when a task is canceled

            # Perform final cleanup
            await agent_manager.aclose()
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
        {_norm_origin(o) for o in configuration.security.user.authorized_origins}
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
    app.include_router(router)
    logger.info("🧩 All controllers registered.")
    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn app.main:create_app --factory ...")
