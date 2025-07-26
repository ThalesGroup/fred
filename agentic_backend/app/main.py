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

from app.core.agents.agent_manager import AgentManager
from app.core.feedback.feedback_controller import FeedbackController
from app.core.monitoring.node_monitoring.node_metric_store import create_node_metric_store
from app.core.monitoring.node_monitoring.node_metric_store_controller import NodeMetricStoreController
from app.core.monitoring.tool_monitoring.tool_metric_store import create_tool_metric_store
from app.core.monitoring.tool_monitoring.tool_metric_store_controller import ToolMetricStoreController
from app.features.frugal.ai_service import AIService
from app.features.frugal.carbon.carbon_controller import CarbonController
from app.features.frugal.energy.energy_controller import EnergyController
from app.features.frugal.finops.finops_controller import FinopsController
from app.core.agents.agent_controller import AgentController
from app.features.k8.kube_service import KubeService
from app.application_context import ApplicationContext, get_agent_store, get_sessions_store
from app.core.chatbot.chatbot_controller import ChatbotController
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.features.frugal.ai_controller import AIController
from app.core.session.session_manager import SessionManager
from app.features.frugal.frontend_controller import UiController
from app.features.k8.kube_controller import KubeController
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

    initialize_keycloak(configuration)
    create_tool_metric_store(configuration.tool_metrics_storage)
    create_node_metric_store(configuration.node_metrics_storage)
    agent_manager = AgentManager(configuration, get_agent_store())
    session_manager = SessionManager(session_storage=get_sessions_store(), agent_manager=agent_manager)

    async def lifespan(app: FastAPI):
        await agent_manager.load_agents()
        logger.info("🚀 AgentManager fully loaded.")
        yield

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
        lifespan=lifespan, 
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.security.authorized_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"], 
        allow_headers=["Content-Type", "Authorization"],
    )

    #@asynccontextmanager
    async def lifespan(app: FastAPI):
        await agent_manager.load_agents()
        logger.info("🚀 AgentManager fully loaded.")
        yield

    router = APIRouter(prefix=base_url)
    enable_k8_features = configuration.frontend_settings.feature_flags.enableK8Features
    if enable_k8_features:
        kube_service = KubeService()
        ai_service = AIService(kube_service)
        KubeController(router)
        AIController(router, ai_service)
        UiController(router, kube_service, ai_service)
        CarbonController(router)
        EnergyController(router)
        FinopsController(router)

    # Register controllers
    FeedbackController(router, configuration.feedback_storage)
    ToolMetricStoreController(router)
    NodeMetricStoreController(router)
    AgentController(router,agent_manager=agent_manager)
    ChatbotController(router, session_manager=session_manager, agent_manager=agent_manager)

    app.include_router(router)
    logger.info("🧩 All controllers registered.")
    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn --factory app.main:create_app ...")