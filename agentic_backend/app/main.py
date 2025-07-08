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
The entrypoint for the Fred microservice.
"""

import argparse
import logging
import os

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.monitoring.tool_monitoring.tool_metric_store import create_tool_metric_store
from app.monitoring.tool_monitoring.tool_metric_store_controller import ToolMetricStoreController
from app.monitoring.node_monitoring.node_metric_store import create_node_metric_store
from app.monitoring.node_monitoring.node_metric_store_controller import NodeMetricStoreController

from services.ai.ai_service import AIService
from services.kube.kube_service import KubeService
from dotenv import load_dotenv
import uvicorn

from app.common.structure import Configuration
from app.common.utils import parse_server_configuration
from app.application_context import ApplicationContext
from app.security.keycloak import initialize_keycloak
from app.main_utils import configure_logging

from app.chatbot.chatbot_controller import ChatbotController
from app.feedback.feedback_controller import FeedbackController
from app.services.frontend.frontend_controller import UiController
from app.services.kube.kube_controller import KubeController
from app.services.ai.ai_controller import AIController
from app.services.carbon.carbon_controller import CarbonController
from app.services.energy.energy_controller import EnergyController
from app.services.finops.finops_controller import FinopsController
from app.services.theater_analysis.theater_analysis_controller import TheaterAnalysisController
from app.services.mission.mission_controller import MissionController
from app.services.theorical_radio.theorical_radio_controller import TheoricalRadioController
from app.services.sensor.sensor_controller import SensorController, SensorConfigurationController

logger = logging.getLogger(__name__)


def load_environment():
    env_path = "./config/.env"
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
        logger.info(f"Loaded environment variables from {env_path}")
    else:
        logger.warning(f"No .env file found at {env_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Fred microservice")
    parser.add_argument("--server.address", dest="server_address", default="0.0.0.0")
    parser.add_argument("--server.port", dest="server_port", type=int, default=8000)
    parser.add_argument("--server.baseUrlPath", dest="server_base_url_path", default="/agentic/v1")
    parser.add_argument("--server.configurationPath", dest="server_configuration_path", default="./config/configuration.yaml")
    parser.add_argument("--server.logLevel", dest="server_log_level", default="info")
    return parser.parse_args()


def build_app(configuration: Configuration, base_url: str) -> FastAPI:
    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json"
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

    # Add controllers
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
    return app


def run_server(app: FastAPI, host: str, port: int, log_level: str):
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        loop="asyncio"
    )

def main():
    load_environment()
    args = parse_args()
    configure_logging()

    configuration: Configuration = parse_server_configuration(args.server_configuration_path)
    ApplicationContext(configuration)
    initialize_keycloak(configuration)

    create_tool_metric_store(configuration.node_metrics_storage)
    create_node_metric_store(configuration.tool_metrics_storage)
    app = build_app(configuration, args.server_base_url_path)
    run_server(app, args.server_address, args.server_port, args.server_log_level)


if __name__ == "__main__":
    main()
