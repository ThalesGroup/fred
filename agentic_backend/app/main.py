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

from app.core.agents.agent_manager import AgentManager
from app.core.chatbot.session_orchestrator import SessionOrchestrator
from app.core.feedback.controller import FeedbackController
from app.core.agents.agent_controller import AgentController
from app.application_context import (
    ApplicationContext,
    get_agent_store,
    get_session_store,
)
from app.core.chatbot.chatbot_controller import ChatbotController
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.core.monitoring.monitoring_controller import MonitoringController
from app.core.prompts.controller import PromptController
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import initialize_keycloak
from rich.logging import RichHandler


# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logger = logging.getLogger(__name__)


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

    initialize_keycloak(configuration.app.security)
    agent_manager = AgentManager(configuration, get_agent_store())
    session_orchestrator = SessionOrchestrator(get_session_store(), agent_manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await agent_manager.load_agents()
            agent_manager.start_retry_loop()
            logger.info("🚀 AgentManager fully loaded.")
            yield
        except asyncio.CancelledError as e:
            logger.warning(
                "🧯 Lifespan CancelledError caught (expected on shutdown): %r", e
            )
            # IMPORTANT: do NOT re-raise; cancellation is a control signal.
            # Swallowing it here prevents the noisy traceback you observed.
        finally:
            logger.info("🧹 Lifespan exit.")

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.app.security.authorized_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    router = APIRouter(prefix=base_url)
    # Register controllers
    FeedbackController(router)
    PromptController(router)
    AgentController(router, agent_manager=agent_manager)

    ChatbotController(
        router, session_orchestrator=session_orchestrator, agent_manager=agent_manager
    )
    MonitoringController(router)
    app.include_router(router)
    logger.info("🧩 All controllers registered.")
    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn app.main:create_app --factory ...")
