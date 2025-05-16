#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The entrypoint for the Fred microservice.
"""

import argparse
from contextlib import asynccontextmanager
import logging
import os
import sys
from copy import deepcopy

import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from context.context_controller import ContextController
from rich.logging import RichHandler

from common.structure import Configuration
from common.utils import parse_server_configuration
from chatbot.chatbot_controller import ChatbotController
from fred.application_context import ApplicationContext
from fred.services.ai.ai_service import AIService
from fred.services.kube.kube_service import KubeService
from security.keycloak import initialize_keycloak
from services.frontend.frontend_controller import UiController
from services.kube.kube_controller import KubeController
from services.ai.ai_controller import AIController
from services.carbon.carbon_controller import CarbonController
from services.energy.energy_controller import EnergyController
from services.finops.finops_controller import FinopsController
from services.theater_analysis.theater_analysis_controller import TheaterAnalysisController
from services.mission.mission_controller import MissionController
from services.theorical_radio.theorical_radio_controller import TheoricalRadioController
from services.sensor.sensor_controller import SensorController
from services.sensor.sensor_controller import SensorConfigurationController
from services.frontend.feedback_router import router as feedback_router
from common.connectors.database import get_engine, initialize_feedback_db
from services.frontend.feedback_router import Base  # This Base is your declarative base for models

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()


def usage():
    """
    Prints the usage instructions for the script.
    """
    print(f"Usage:\n{sys.argv[0]} <configuration file>")


def main():
    """
    Main function to run the Fred microservice.

    Parses command-line arguments, configures the FastAPI application,
    and starts the Uvicorn server.
    """
    parser = argparse.ArgumentParser(
        description="Fred microservice", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--server.address",
        dest="server_address",
        type=str,
        help="Specify the address of the server",
        default="0.0.0.0",
    )
    parser.add_argument(
        "--server.port",
        dest="server_port",
        type=int,
        help="Specify the port of the server",
        default=8000,
    )
    parser.add_argument(
        "--server.baseUrlPath",
        dest="server_base_url_path",
        type=str,
        help="Specify the base url for the API entrypoints",
        default="/fred",
    )
    parser.add_argument(
        "--server.configurationPath",
        dest="server_configuration_path",
        type=str,
        help="Specify the path of the configuration used",
        default="./config/configuration.yaml",
    )
    parser.add_argument(
        "--server.logLevel",
        dest="server_log_level",
        type=str,
        help="Specify the log level of the server",
        default="info",
    )
    args = parser.parse_args()

    # Parse configuration and initialize Keycloak and feedback DB
    configuration: Configuration = parse_server_configuration(
        args.server_configuration_path
    )
    ApplicationContext(configuration)
    initialize_keycloak(configuration)
    

    # TODO FEEDBACK: Initialize feedback database
    # Define a lifespan event handler using an async context manager.
    #initialize_feedback_db(configuration)
    #@asynccontextmanager
    #async def lifespan(app: FastAPI):
    #    try:
    #      # Create database tables; this is synchronous and acceptable for startup.
    #        engine = get_engine()
    #        Base.metadata.create_all(bind=engine)
    #        logger.info("Feedback database tables created successfully.")
    #    except Exception as e:
    #        logger.error("Feedback database initialization failed: %s. Some services may trigger 500 errors.", e)
    #    yield

    # Create FastAPI app with lifespan event.
    logger.info(f"FastAPI server base URL path: {args.server_base_url_path}")
    app = FastAPI(
        # TODO FEEDBACK lifespan=lifespan,
        docs_url=f"{args.server_base_url_path}/docs",
        redoc_url=f"{args.server_base_url_path}/redoc",
        openapi_url=f"{args.server_base_url_path}/openapi.json",
    )

    # Add CORS middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Create an API router with the given base URL prefix.
    router = APIRouter(prefix=args.server_base_url_path)

    # Initialize and add controllers.    
    kube_service = KubeService()
    ai_service = AIService(kube_service)
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
    ContextController(router)
    app.include_router(router)
    app.include_router(feedback_router)

    # Run the server.
    uvicorn.run(
        app,
        host=args.server_address,
        port=args.server_port,
        log_level=args.server_log_level,
    )

def configure_logging():
    """Configure logging dynamically based on LOG_LEVEL environment variable."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        log_level = "INFO"
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False)],
    )
    logging.getLogger().info(f"Logging configured at {log_level} level.")


if __name__ == "__main__":
    configure_logging()
    main()
