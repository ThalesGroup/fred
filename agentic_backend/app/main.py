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

import argparse
import logging

import uvicorn
from app.application_context import ApplicationContext
from app.chatbot.chatbot_controller import ChatbotController
from app.common.structure import Configuration
from app.common.utils import parse_server_configuration
from app.feedback.feedback_controller import FeedbackController
from app.monitoring.node_monitoring.node_metric_store import \
    create_node_metric_store
from app.monitoring.node_monitoring.node_metric_store_controller import \
    NodeMetricStoreController
from app.monitoring.tool_monitoring.tool_metric_store import \
    create_tool_metric_store
from app.monitoring.tool_monitoring.tool_metric_store_controller import \
    ToolMetricStoreController
from app.security.keycloak import initialize_keycloak
from app.services.ai.ai_controller import AIController
from app.services.carbon.carbon_controller import CarbonController
from app.services.energy.energy_controller import EnergyController
from app.services.finops.finops_controller import FinopsController
from app.services.frontend.frontend_controller import UiController
from app.services.kube.kube_controller import KubeController
from app.services.mission.mission_controller import MissionController
from app.services.sensor.sensor_controller import (
    SensorConfigurationController, SensorController)
from app.services.theater_analysis.theater_analysis_controller import \
    TheaterAnalysisController
from app.services.theorical_radio.theorical_radio_controller import \
    TheoricalRadioController
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.logging import RichHandler
from services.ai.ai_service import AIService
from services.kube.kube_service import KubeService


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
# CLI ARGUMENTS
# -----------------------


def parse_cli_opts():
    parser = argparse.ArgumentParser(description="Start the Agentic Backend App")
    parser.add_argument(
        "--config-path",
        default="./config/configuration.yaml",
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--base-url",
        default="/agentic/v1",
        help="Base path for all API endpoints",
    )
    parser.add_argument(
        "--server-address", default="127.0.0.1", help="Server binding address"
    )
    parser.add_argument("--server-port", type=int, default=8000, help="Server port")
    parser.add_argument("--log-level", default="info", help="Logging level")
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (for dev only)"
    )
    parser.add_argument(
        "--reload-dir", default=".", help="Watch for changes in these directories"
    )

    return parser.parse_args()


# -----------------------
# APP CREATION
# -----------------------


def create_app(config_path: str, base_url: str) -> FastAPI:
    logger.info(f"🛠️ create_app() called with base_url={base_url}")

    configuration: Configuration = parse_server_configuration(config_path)
    ApplicationContext(configuration)  # 🟢 harmonisation ici

    initialize_keycloak(configuration)
    create_tool_metric_store(configuration.node_metrics_storage)
    create_node_metric_store(configuration.tool_metrics_storage)

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.security.authorized_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    router = APIRouter(prefix=base_url)

    # Initialize services
    kube_service = KubeService()
    ai_service = AIService(kube_service)

    # Register controllers
    SensorController(router)
    SensorConfigurationController(router)
    TheaterAnalysisController(router)
    MissionController(router)
    TheoricalRadioController(router)
    CarbonController(router)
    EnergyController(router)
    FinopsController(router)
    KubeController(router)
    AIController(router, ai_service)
    UiController(router, kube_service, ai_service)
    ChatbotController(router, ai_service)
    FeedbackController(router, configuration.feedback_storage)
    ToolMetricStoreController(router)
    NodeMetricStoreController(router)

    app.include_router(router)
    logger.info("🧩 All controllers registered.")
    return app


# -----------------------
# MAIN ENTRYPOINT
# -----------------------


def main():
    args = parse_cli_opts()
    configure_logging(args.log_level)
    load_environment()

    app = create_app(config_path=args.config_path, base_url=args.base_url)

    uvicorn.run(
        app,
        host=args.server_address,
        port=args.server_port,
        log_level=args.log_level,
        loop="asyncio",
        reload=args.reload,
        reload_dirs=args.reload_dir,
    )


if __name__ == "__main__":
    main()

# Note: We do not define a global `app = FastAPI()` for ASGI (e.g., `uvicorn app.main:app`)
# because this application is always launched via the CLI `main()` function.
# This allows full control over configuration (e.g., --config-path, --base-url) and avoids
# the need for a static app instance required by ASGI-based servers like Uvicorn in import mode.
