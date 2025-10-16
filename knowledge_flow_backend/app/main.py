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

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import AuthConfig, FastApiMCP
from fred_core import get_current_user, initialize_user_security, log_setup, register_exception_handlers

from app.application_context import ApplicationContext
from app.application_state import attach_app
from app.common.http_logging import RequestResponseLogger
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.core.monitoring.monitoring_controller import MonitoringController
from app.features.catalog.controller import CatalogController
from app.features.content import report_controller
from app.features.content.asset_controller import AssetController
from app.features.content.content_controller import ContentController
from app.features.ingestion.controller import IngestionController
from app.features.kpi import logs_controller
from app.features.kpi.kpi_controller import KPIController
from app.features.kpi.opensearch_controller import OpenSearchOpsController
from app.features.metadata.controller import MetadataController
from app.features.pull.controller import PullDocumentController
from app.features.pull.service import PullDocumentService
from app.features.resources.controller import ResourceController
from app.features.scheduler.controller import SchedulerController
from app.features.tabular.controller import TabularController
from app.features.tag.controller import TagController
from app.features.vector_search.vector_search_controller import VectorSearchController
from app.security.keycloak_rebac_sync import reconcile_keycloak_groups_with_rebac

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

    if not configuration.processing.use_gpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["MPS_VISIBLE_DEVICES"] = ""
        import torch

        torch.set_default_device("cpu")
        logger.warning("⚠️ GPU support is disabled. Running on CPU.")

    application_context = ApplicationContext(configuration)
    log_setup(
        service_name="knowledge-flow",
        log_level=configuration.app.log_level,
        store=application_context.get_log_store(),
    )
    logger.info(f"🛠️ create_app() called with base_url={base_url}")
    application_context._log_config_summary()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def periodic_reconciliation() -> None:
            while True:
                try:
                    await reconcile_keycloak_groups_with_rebac()
                except Exception:  # noqa: BLE001
                    logger.exception("Scheduled Keycloak→SpiceDB reconciliation failed.")
                await asyncio.sleep(15 * 60)

        # Reconcile Keycloak groups with ReBAC every 15 minutes
        background_task = asyncio.create_task(periodic_reconciliation())

        try:
            yield
        finally:
            background_task.cancel()
            with suppress(asyncio.CancelledError):
                await background_task

    app = FastAPI(
        docs_url=f"{configuration.app.base_url}/docs",
        redoc_url=f"{configuration.app.base_url}/redoc",
        openapi_url=f"{configuration.app.base_url}/openapi.json",
        lifespan=lifespan,
    )

    # Register exception handlers
    register_exception_handlers(app)
    allowed_origins = list({_norm_origin(o) for o in configuration.security.authorized_origins})
    logger.info("[CORS] allow_origins=%s", allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    initialize_user_security(configuration.security.user)

    app.add_middleware(RequestResponseLogger)
    # Attach FastAPI to build M2M in-process client (lives outside ApplicationContext)
    attach_app(app)

    router = APIRouter(prefix=configuration.app.base_url)

    MonitoringController(router)

    pull_document_service = PullDocumentService()
    # Register controllers
    MetadataController(router, pull_document_service)
    CatalogController(router)
    PullDocumentController(router, pull_document_service)
    ContentController(router)
    AssetController(router)
    IngestionController(router)
    TabularController(router)
    # CodeSearchController(router)
    TagController(app, router)
    ResourceController(router)
    VectorSearchController(router)
    KPIController(router)
    OpenSearchOpsController(router)
    router.include_router(logs_controller.router)
    router.include_router(report_controller.router)
    if configuration.scheduler.enabled:
        logger.info("🧩 Activating ingestion scheduler controller.")
        SchedulerController(router)

    logger.info("🧩 All controllers registered.")
    app.include_router(router)
    mcp_prefix = "/knowledge-flow/v1"

    # mcp_agent_assets = FastApiMCP(
    #     app,
    #     name="Knowledge Flow Agent Assets MCP",
    #     description=(
    #         "CRUD interface for per-user and per agent assets (e.g., PPTX templates). "
    #         "Use this MCP to manage binary assets scoped to specific agents and users. "
    #         "Supports upload, retrieval (with Range), listing, and deletion of assets. "
    #         "Ensures clear tenancy boundaries and authorization for secure asset management."
    #     ),
    #     include_tags=["Agent Assets"],
    #     describe_all_responses=True,
    #     describe_full_response_schema=True,
    #     auth_config=AuthConfig(dependencies=[Depends(get_current_user)]),
    # )
    # mcp_agent_assets.mount_http(mount_path=f"{mcp_prefix}/mcp-assets")
    logger.info(f"🔌 MCP Agent Assets mounted at {mcp_prefix}/mcp-agent-assets")
    mcp_reports = FastApiMCP(
        app,
        name="Knowledge Flow Reports MCP",
        description="Create Markdown-first reports and get downloadable artifacts.",
        include_tags=["Reports"],  # ← export only these routes as tools
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=AuthConfig(dependencies=[Depends(get_current_user)]),
    )
    mcp_reports.mount_http(mount_path=f"{mcp_prefix}/mcp-reports")
    mcp_opensearch_ops = FastApiMCP(
        app,
        name="Knowledge Flow OpenSearch Ops MCP",
        description=("Read-only operational tools for OpenSearch: cluster health, nodes, shards, indices, mappings, and sample docs. Monitoring/diagnostics only."),
        include_tags=["OpenSearch"],  # <-- only export routes tagged OpenSearch as MCP tools
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    # Mount via HTTP at a clear, versioned path:
    mcp_mount_path = f"{mcp_prefix}/mcp-opensearch-ops"
    mcp_opensearch_ops.mount_http(mount_path=mcp_mount_path)
    logger.info(f"🔌 MCP OpenSearch Ops mounted at {mcp_mount_path}")
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
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_kpi.mount_http(mount_path=f"{mcp_prefix}/mcp-kpi")

    mcp_tabular = FastApiMCP(
        app,
        name="Knowledge Flow Tabular MCP",
        description=(
            "SQL access layer exposed through SQLAlchemy. "
            "Provides agents with read and query capabilities over relational data "
            "from configured backends (e.g. PostgreSQL, MySQL, SQLite). "
            "Use this MCP to explore table schemas, run SELECT queries, and analyze tabular datasets. "
            "Create, update and drop tables if asked by the user if allowed."
        ),
        include_tags=["Tabular"],
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_tabular.mount_http(mount_path=f"{mcp_prefix}/mcp-tabular")

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
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_text.mount_http(mount_path=f"{mcp_prefix}/mcp-text")

    mcp_template = FastApiMCP(
        app,
        name="Knowledge Flow Text MCP",
        description="MCP server for Knowledge Flow Text",
        include_tags=["Templates", "Prompts"],
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_template.mount_http(mount_path=f"{mcp_prefix}/mcp-template")

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
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_code.mount_http(mount_path=f"{mcp_prefix}/mcp-code")

    mcp_resources = FastApiMCP(
        app,
        name="Knowledge Flow Resources MCP",
        description=(
            "Access to reusable resources for agents. "
            "Provides prompts, templates, and other content assets that can be used "
            "to customize agent behavior or generate well-structured custom reports. "
            "Use this MCP to browse, retrieve, and apply predefined resources when composing answers or building workflows."
        ),
        include_tags=["Resources", "Tags"],
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
            dependencies=[Depends(get_current_user)]
        ),
    )
    mcp_resources.mount_http(mount_path=f"{mcp_prefix}/mcp-resources")

    return app


# -----------------------
# MAIN ENTRYPOINT
# -----------------------

if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn app.main:create_app --factory ...")
