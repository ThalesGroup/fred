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
from rich.logging import RichHandler
from dotenv import load_dotenv

from app.features.catalog.controller import CatalogController
from app.features.kpi.kpi_controller import KPIController
from app.features.kpi.oensearch_controller import OpenSearchOpsController
from app.features.pull.controller import PullDocumentController
from app.features.pull.service import PullDocumentService
from app.features.resources.controller import ResourceController
from app.features.scheduler.controller import SchedulerController
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from fred_core import initialize_keycloak

from app.application_context import ApplicationContext
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.features.content.controller import ContentController
from app.features.metadata.controller import MetadataController
from app.features.tabular.controller import TabularController
from app.features.tag.controller import TagController
from app.features.vector_search.controller import VectorSearchController
from app.features.ingestion.controller import IngestionController

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
    logging.getLogger(__name__).info(f"Logging configured at {log_level.upper()} level.")


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

    app = FastAPI(
        docs_url=f"{configuration.app.base_url}/docs",
        redoc_url=f"{configuration.app.base_url}/redoc",
        openapi_url=f"{configuration.app.base_url}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.app.security.authorized_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    router = APIRouter(prefix=configuration.app.base_url)

    pull_document_service = PullDocumentService()
    # Register controllers
    MetadataController(router, pull_document_service)
    CatalogController(router)
    PullDocumentController(router, pull_document_service)
    ContentController(router)
    IngestionController(router)
    TabularController(router)
    # CodeSearchController(router)
    TagController(router)
    ResourceController(router)
    VectorSearchController(router)
    KPIController(router)
    OpenSearchOpsController(router)

    if configuration.scheduler.enabled:
        logger.info("🧩 Activating ingestion scheduler controller.")
        SchedulerController(router)

    logger.info("🧩 All controllers registered.")
    app.include_router(router)

    mcp_opensearch_ops = FastApiMCP(
        app,
        name="Knowledge Flow OpenSearch Ops MCP",
        description=(
            "Read-only operational tools for OpenSearch. "
            "Use these endpoints to inspect cluster health, node and shard status, "
            "list indices, view mappings, and fetch sample documents. "
            "Intended for monitoring and diagnostics, not for modifying data."
        ),
        include_tags=["OpenSearch"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_opensearch_ops.mount(mount_path="/mcp_opensearch_ops")

    mcp_kpi = FastApiMCP(
        app,
        name="Knowledge Flow KPI MCP",
        description=(
            "Query interface for application KPIs. "
            "Use these endpoints to run structured aggregations over metrics "
            "(e.g. vectorization latency, LLM usage, token costs, error counts). "
            "Provides schema, presets, and query compilation helpers so agents can "
            "form valid KPI queries without guessing."
        ),
        include_tags=["KPI"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_kpi.mount(mount_path="/mcp_kpi")

    mcp_tabular = FastApiMCP(
        app,
        name="Knowledge Flow Tabular MCP",
        description=(
            "SQL access layer exposed through SQLAlchemy. "
            "Provides agents with read and query capabilities over relational data "
            "from configured backends (e.g. PostgreSQL, MySQL, SQLite). "
            "Use this MCP to explore table schemas, run SELECT queries, and analyze tabular datasets. "
            "It does not modify or write data."
        ),
        include_tags=["Tabular"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_tabular.mount(mount_path="/mcp_tabular")

    mcp_text = FastApiMCP(
        app,
        name="Knowledge Flow Text MCP",
        description=(
            "Semantic text search interface backed by the vector store. "
            "Use this MCP to perform vector similarity search over ingested documents, "
            "retrieve relevant passages, and ground answers in source material. "
            "It supports queries by text embedding rather than keyword match."
        ),
        include_tags=["Vector Search"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_text.mount(mount_path="/mcp_text")

    mcp_template = FastApiMCP(
        app,
        name="Knowledge Flow Text MCP",
        description="MCP server for Knowledge Flow Text",
        include_tags=["Templates", "Prompts"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_template.mount(mount_path="/mcp_template")

    mcp_code = FastApiMCP(
        app,
        name="Knowledge Flow Code MCP",
        description=(
            "Codebase exploration and search interface. "
            "Use this MCP to scan and query code repositories, find relevant files, "
            "and retrieve snippets or definitions. "
            "Currently supports basic search, with planned improvements for deeper analysis "
            "such as symbol navigation, dependency mapping, and code understanding."
        ),
        include_tags=["Code Search"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_code.mount(mount_path="/mcp_code")

    mcp_resources = FastApiMCP(
        app,
        name="Knowledge Flow Resources MCP",
        description=(
            "Access to reusable resources for agents. "
            "Provides prompts, templates, and other content assets that can be used "
            "to customize agent behavior or generate well-structured custom reports. "
            "Use this MCP to browse, retrieve, and apply predefined resources when composing answers or building workflows."
        ),
        include_tags=["Resources"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_resources.mount(mount_path="/mcp_resources")

    return app


# -----------------------
# MAIN ENTRYPOINT
# -----------------------

if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn --factory app.main:create_app ...")
