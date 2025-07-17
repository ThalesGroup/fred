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
Entrypoint for the Knowledge Flow Backend App.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from fred_core import initialize_keycloak
from rich.logging import RichHandler

from app.application_context import ApplicationContext
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.features.code_search.controller import CodeSearchController
from app.features.content.controller import ContentController
from app.features.metadata.controller import MetadataController
from app.features.tabular.controller import TabularController
from app.features.tag.controller import TagController
from app.features.vector_search.controller import VectorSearchController
from app.features.wip.ingestion_controller import IngestionController
from app.features.wip.knowledge_context_controller import KnowledgeContextController

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
    configure_logging(os.getenv("LOG_LEVEL", "info"))

    # Retrieve config path
    config_file = os.getenv("CONFIG_FILE")
    if ApplicationContext._instance is None:
        if config_file is None:
            raise ValueError("CONFIG_FILE is required if ApplicationContext is not already initialized")
        configuration: Configuration = parse_server_configuration(config_file)
        ApplicationContext(configuration)
    else:
        # Get config from pre-initialized ApplicationContext (e.g. in tests)
        configuration = ApplicationContext.get_instance().get_config()

    base_url = configuration.v1_base_url
    logger.info(f"🛠️ create_app() called with base_url={base_url}")

    initialize_keycloak(configuration)

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

    # Register controllers
    IngestionController(router)
    VectorSearchController(router)
    MetadataController(router)
    ContentController(router)
    KnowledgeContextController(router)
    TabularController(router)
    CodeSearchController(router)
    TagController(router)

    logger.info("🧩 All controllers registered.")
    app.include_router(router)
    logger.info("🧩 All controllers registered.")

    mcp_tabular = FastApiMCP(
        app,
        name="Knowledge Flow Tabular MCP",
        description="MCP server for Knowledge Flow Tabular",
        include_tags=["Tabular"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_tabular.mount(mount_path="/mcp_tabular")
    mcp_text = FastApiMCP(
        app,
        name="Knowledge Flow Text MCP",
        description="MCP server for Knowledge Flow Text",
        include_tags=["Vector Search"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_text.mount(mount_path="/mcp_text")
    mcp_code = FastApiMCP(
        app,
        name="Knowledge Flow Code MCP",
        description="MCP server for Knowledge Flow Codebase features",
        include_tags=["Code Search"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_code.mount(mount_path="/mcp_code")

    return app


if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn --factory app.main:create_app ...")
