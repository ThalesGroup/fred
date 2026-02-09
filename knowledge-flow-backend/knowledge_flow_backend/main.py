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

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import AuthConfig, FastApiMCP
from fred_core import (
    get_current_user,
    initialize_user_security,
    log_setup,
    register_exception_handlers,
)
from fred_core.kpi import emit_process_kpis
from fred_core.scheduler import TemporalClientProvider
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.application_state import attach_app
from knowledge_flow_backend.common.http_logging import RequestResponseLogger
from knowledge_flow_backend.common.structures import Configuration
from knowledge_flow_backend.common.utils import parse_server_configuration
from knowledge_flow_backend.compat import fastapi_mcp_patch  # noqa: F401
from knowledge_flow_backend.core.monitoring.monitoring_controller import (
    MonitoringController,
)
from knowledge_flow_backend.features.benchmark.benchmark_controller import BenchmarkController
from knowledge_flow_backend.features.content import report_controller
from knowledge_flow_backend.features.content.asset_controller import AssetController
from knowledge_flow_backend.features.content.content_controller import ContentController
from knowledge_flow_backend.features.corpus_manager.corpus_manager_controller import CorpusManagerController
from knowledge_flow_backend.features.filesystem.mcp_fs_controller import McpFilesystemController
from knowledge_flow_backend.features.filesystem.workspace_storage_controller import WorkspaceStorageController
from knowledge_flow_backend.features.groups import groups_controller
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from knowledge_flow_backend.features.kpi import logs_controller
from knowledge_flow_backend.features.kpi.kpi_controller import KPIController
from knowledge_flow_backend.features.kpi.opensearch_controller import (
    OpenSearchOpsController,
)
from knowledge_flow_backend.features.metadata.controller import MetadataController
from knowledge_flow_backend.features.model.controller import ModelController
from knowledge_flow_backend.features.neo4j.neo4j_controller import Neo4jController
from knowledge_flow_backend.features.resources.controller import ResourceController
from knowledge_flow_backend.features.scheduler.scheduler_controller import SchedulerController
from knowledge_flow_backend.features.statistic.controller import StatisticController
from knowledge_flow_backend.features.tabular.controller import TabularController
from knowledge_flow_backend.features.tag.tag_controller import TagController
from knowledge_flow_backend.features.users import users_controller
from knowledge_flow_backend.features.vector_search.vector_search_controller import (
    VectorSearchController,
)
from knowledge_flow_backend.security.keycloak_rebac_sync import (
    reconcile_keycloak_groups_with_rebac,
)

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOG_PREFIX = "[APP]"


def _norm_origin(o) -> str:
    # Ensure exact match with browser's Origin header (no trailing slash)
    return str(o).rstrip("/")


def load_environment(dotenv_path: str = "./config/.env"):
    if load_dotenv(dotenv_path):
        logger.info("%s Loaded environment variables from: %s", LOG_PREFIX, dotenv_path)
    else:
        logger.warning("%s No .env file found at: %s", LOG_PREFIX, dotenv_path)


def load_configuration():
    load_environment()
    config_file = os.environ.get("CONFIG_FILE", "./config/configuration.yaml")
    configuration: Configuration = parse_server_configuration(config_file)
    logger.info("%s Loaded configuration from: %s", LOG_PREFIX, config_file)
    return configuration


# -----------------------
# APP CREATION
# -----------------------


def create_app() -> FastAPI:
    configuration: Configuration = load_configuration()
    logger.info("%s Embedding model: [%s] %s", LOG_PREFIX, configuration.embedding_model.provider, configuration.embedding_model.name)
    logger.info("%s Chat model: [%s] %s", LOG_PREFIX, configuration.chat_model.provider, configuration.chat_model.name)

    base_url = configuration.app.base_url

    if not configuration.processing.use_gpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["MPS_VISIBLE_DEVICES"] = ""
        import torch

        torch.set_default_device("cpu")
        logger.warning("%s GPU support is disabled. Running on CPU.", LOG_PREFIX)

    application_context = ApplicationContext(configuration)
    log_setup(
        service_name="knowledge-flow",
        log_level=configuration.app.log_level,
        store=application_context.get_log_store(),
    )
    logger.info("%s create_app() called with base_url=%s", LOG_PREFIX, base_url)
    application_context._log_config_summary()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def periodic_reconciliation() -> None:
            while True:
                try:
                    await reconcile_keycloak_groups_with_rebac()
                except Exception:  # noqa: BLE001
                    logger.exception("%s Scheduled Keycloak→Rebac reconciliation failed.", LOG_PREFIX)
                await asyncio.sleep(15 * 60)

        # Reconcile Keycloak groups with ReBAC every 15 minutes
        background_task = asyncio.create_task(periodic_reconciliation())
        process_kpi_task = None
        kpi_interval_env = configuration.app.kpi_process_metrics_interval_sec
        if kpi_interval_env:
            try:
                interval_s = float(kpi_interval_env)
            except ValueError:
                logger.error(
                    "Invalid KPI process metrics interval: %s. Disabling KPI process metrics task.",
                    kpi_interval_env,
                )
                interval_s = 0
            if interval_s > 0:
                process_kpi_task = asyncio.create_task(emit_process_kpis(interval_s, application_context.get_kpi_writer()))

        try:
            yield
        finally:
            if process_kpi_task:
                process_kpi_task.cancel()
                with suppress(asyncio.CancelledError):
                    await process_kpi_task
            background_task.cancel()
            with suppress(asyncio.CancelledError):
                await background_task
            await application_context.shutdown()

    app = FastAPI(
        docs_url=f"{configuration.app.base_url}/docs",
        redoc_url=f"{configuration.app.base_url}/redoc",
        openapi_url=f"{configuration.app.base_url}/openapi.json",
        lifespan=lifespan,
    )

    if configuration.app.metrics_enabled:
        Instrumentator().instrument(app)
        start_http_server(
            configuration.app.metrics_port,
            addr=configuration.app.metrics_address,
        )

    # Register exception handlers
    register_exception_handlers(app)
    allowed_origins = list({_norm_origin(o) for o in configuration.security.authorized_origins})
    logger.info("%s[CORS] allow_origins=%s", LOG_PREFIX, allowed_origins)
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

    # Register base controllers. These are the one always needed.
    MetadataController(router)
    ModelController(router)
    ContentController(router)
    AssetController(router)
    WorkspaceStorageController(router)
    IngestionController(router)
    TagController(app, router)
    VectorSearchController(router)
    KPIController(router)
    ResourceController(router)
    McpFilesystemController(router)
    CorpusManagerController(router)
    router.include_router(logs_controller.router)
    router.include_router(groups_controller.router)
    router.include_router(users_controller.router)
    # Developer benchmarking tools (always mounted; auth-protected)
    BenchmarkController(router)

    if configuration.mcp.tabular_enabled:
        # Required for Tessa
        TabularController(router)
        logger.info("%s TabularController registered (mcp.tabular_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s TabularController disabled via configuration.mcp.tabular_enabled=false", LOG_PREFIX)

    if configuration.mcp.statistic_enabled:
        # Required for the statistical analysis agent
        StatisticController(router)
        logger.info("%s StatisticController registered (mcp.statistic_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s StatisticController disabled via configuration.mcp.statistic_enabled=false", LOG_PREFIX)

    if configuration.mcp.opensearch_ops_enabled:
        OpenSearchOpsController(router)
        logger.info("%s OpenSearchOpsController registered (mcp.opensearch_ops_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s OpenSearchOpsController disabled via configuration.mcp.opensearch_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.neo4j_enabled:
        Neo4jController(router)
        logger.info("%s Neo4jController registered (mcp.neo4j_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s Neo4jController disabled via configuration.mcp.neo4j_enabled=false", LOG_PREFIX)

    if configuration.mcp.reports_enabled:
        logger.info("%s ReportsController registered (mcp.reports_enabled=true)", LOG_PREFIX)
        router.include_router(report_controller.router)
    else:
        logger.warning("%s ReportsController disabled via configuration.mcp.reports_enabled=false", LOG_PREFIX)

    if configuration.scheduler.enabled:
        logger.info("%s Activating ingestion scheduler controller.", LOG_PREFIX)
        temporal_client_provider = None

        if configuration.scheduler.backend.lower() == "temporal":
            temporal_cfg = configuration.scheduler.temporal
            if not temporal_cfg:
                raise ValueError("Scheduler enabled with temporal backend but temporal configuration is missing!")
            if not temporal_cfg.task_queue:
                raise ValueError("Scheduler enabled but Temporal task_queue is not set in configuration!")
            temporal_client_provider = TemporalClientProvider(temporal_cfg)

        SchedulerController(router, temporal_client_provider=temporal_client_provider)
    else:
        logger.warning("%s Ingestion scheduler controller disabled via configuration.scheduler.enabled=false", LOG_PREFIX)

    logger.info("%s All controllers registered.", LOG_PREFIX)
    app.include_router(router)
    mcp_prefix = "/knowledge-flow/v1"

    logger.info("%s MCP Agent Assets mounted at %s/mcp-agent-assets", LOG_PREFIX, mcp_prefix)
    auth_cfg: AuthConfig = AuthConfig(dependencies=[Depends(get_current_user)])
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
    #     auth_config=auth_cfg,
    # )
    # mcp_agent_assets.mount_http(mount_path=f"{mcp_prefix}/mcp-assets")
    mcp_reports = FastApiMCP(
        app,
        name="Knowledge Flow Reports MCP",
        description="Create Markdown-first reports and get downloadable artifacts.",
        include_tags=["Reports"],  # ← export only these routes as tools
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=auth_cfg,
    )
    mcp_reports.mount_http(mount_path=f"{mcp_prefix}/mcp-reports")

    # Optional MCP servers: they export only the tagged routes above.
    if configuration.mcp.opensearch_ops_enabled:
        mcp_opensearch_ops = FastApiMCP(
            app,
            name="Knowledge Flow OpenSearch Ops MCP",
            description=("Read-only operational tools for OpenSearch: cluster health, nodes, shards, indices, mappings, and sample docs. Monitoring/diagnostics only."),
            include_tags=["OpenSearch"],  # <-- only export routes tagged OpenSearch as MCP tools
            describe_all_responses=True,
            describe_full_response_schema=True,
            auth_config=auth_cfg,
        )
        # Mount via HTTP at a clear, versioned path:
        mcp_mount_path = f"{mcp_prefix}/mcp-opensearch-ops"
        mcp_opensearch_ops.mount_http(mount_path=mcp_mount_path)
        logger.info("%s MCP OpenSearch Ops mounted at %s", LOG_PREFIX, mcp_mount_path)
    else:
        logger.warning("%s MCP OpenSearch Ops disabled via configuration.mcp.opensearch_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.neo4j_enabled:
        mcp_neo4j = FastApiMCP(
            app,
            name="Knowledge Flow Neo4j MCP",
            description=(
                "Read-only graph exploration interface backed by Neo4j. "
                "Use this MCP to inspect labels and relationship types, "
                "sample local neighborhoods, and run parameterized MATCH/RETURN "
                "Cypher queries for graph-based reasoning."
            ),
            include_tags=["Neo4j"],
            describe_all_responses=True,
            describe_full_response_schema=True,
            auth_config=auth_cfg,
        )
        neo4j_mount_path = f"{mcp_prefix}/mcp-neo4j"
        mcp_neo4j.mount_http(mount_path=neo4j_mount_path)
        logger.info("%s MCP Neo4j mounted at %s", LOG_PREFIX, neo4j_mount_path)
    else:
        logger.warning("%s MCP Neo4j disabled via configuration.mcp.neo4j_enabled=false", LOG_PREFIX)

    if configuration.mcp.kpi_enabled:
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
            auth_config=auth_cfg,
        )
        mcp_kpi.mount_http(mount_path=f"{mcp_prefix}/mcp-kpi")
    else:
        logger.warning("%s MCP KPI disabled via configuration.mcp.kpi_enabled=false", LOG_PREFIX)

    if configuration.mcp.tabular_enabled:
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
            auth_config=auth_cfg,
        )
        mcp_tabular.mount_http(mount_path=f"{mcp_prefix}/mcp-tabular")
    else:
        logger.info("%s MCP Tabular disabled via configuration.mcp.tabular_enabled=false", LOG_PREFIX)

    if configuration.mcp.statistic_enabled:
        mcp_statistical = FastApiMCP(
            app,
            name="Knowledge Flow Statistic MCP",
            description=(
                "Provides endpoints to load, explore, and analyze tabular datasets,"
                "including outlier detection and correlation analysis."
                "Supports plotting histograms and scatter plots, plus ML operations:"
                "training, evaluation, saving/loading models, and single-row predictions."
            ),
            include_tags=["Statistic"],
            describe_all_responses=True,
            describe_full_response_schema=True,
            auth_config=AuthConfig(  # <-- protect with your user auth as a normal dependency
                dependencies=[Depends(get_current_user)]
            ),
        )
        mcp_statistical.mount_http(mount_path=f"{mcp_prefix}/mcp-statistic")
    else:
        logger.info("%s MCP Statistic disabled via configuration.mcp.statistic_enabled=false", LOG_PREFIX)

    if configuration.mcp.text_enabled:
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
            auth_config=auth_cfg,
        )
        mcp_text.mount_http(mount_path=f"{mcp_prefix}/mcp-text")
    else:
        logger.info("%s MCP Text disabled via configuration.mcp.text_enabled=false", LOG_PREFIX)

    if configuration.mcp.templates_enabled:
        mcp_template = FastApiMCP(
            app,
            name="Knowledge Flow Text MCP",
            description="MCP server for Knowledge Flow Text",
            include_tags=["Templates", "Prompts"],
            describe_all_responses=True,
            describe_full_response_schema=True,
            auth_config=auth_cfg,
        )
        mcp_template.mount_http(mount_path=f"{mcp_prefix}/mcp-template")
    else:
        logger.info("%s MCP Templates disabled via configuration.mcp.templates_enabled=false", LOG_PREFIX)

    # if configuration.mcp.code_enabled:
    #     mcp_code = FastApiMCP(
    #         app,
    #         name="Knowledge Flow Code MCP",
    #         description=(
    #             "Codebase exploration and search interface. "
    #             "Use this MCP to scan and query code repositories, find relevant files, "
    #             "and retrieve snippets or definitions. "
    #             "Currently supports basic search, with planned improvements for deeper analysis "
    #             "such as symbol navigation, dependency mapping, and code understanding."
    #         ),
    #         include_tags=["Code Search"],
    #         describe_all_responses=True,
    #         describe_full_response_schema=True,
    #         auth_config=auth_cfg,
    #     )
    #     mcp_code.mount_http(mount_path=f"{mcp_prefix}/mcp-code")
    # else:
    #     logger.info("%s MCP Code disabled via configuration.mcp.code_enabled=false", LOG_PREFIX)

    if configuration.mcp.resources_enabled:
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
            auth_config=auth_cfg,
        )
        mcp_resources.mount_http(mount_path=f"{mcp_prefix}/mcp-resources")
    else:
        logger.info("%s MCP Resources disabled via configuration.mcp.resources_enabled=false", LOG_PREFIX)

    if configuration.mcp.filesystem_enabled:
        mcp_fs = FastApiMCP(
            app,
            name="Knowledge Flow Filesystem MCP",
            description=(
                "Provides unified filesystem access for agents. "
                "Exposes a virtual filesystem backed by the server's configured storage "
                "(such as local or MinIO) and allows agents to browse directories, inspect metadata, "
                "read and write files, delete resources, and search content using regex. "
                "Use this MCP when an agent needs to retrieve data, persist intermediate results, "
                "inspect logs, or navigate structured file-based resources during workflow execution."
            ),
            include_tags=["Filesystem"],
            describe_all_responses=True,
            describe_full_response_schema=True,
            auth_config=auth_cfg,
        )

        mcp_fs.mount_http(mount_path=f"{mcp_prefix}/mcp-fs")
    else:
        logger.info("%s MCP Filesystem disabled via configuration.mcp.filesystem_enabled=false", LOG_PREFIX)

    # Corpus manager MCP (mock; exports the HTTP-tagged routes to MCP clients)
    mcp_corpus = FastApiMCP(
        app,
        name="Knowledge Flow Corpus MCP",
        description=("Manage corpora: start TOC builds, revectorize, purge vectors, and poll task status. Mock implementation backed by in-memory tasks for demos."),
        include_tags=["CorpusManager"],
        describe_all_responses=True,
        describe_full_response_schema=True,
        auth_config=auth_cfg,
    )
    mcp_corpus.mount_http(mount_path=f"{mcp_prefix}/mcp-corpus")

    return app


# -----------------------
# MAIN ENTRYPOINT
# -----------------------

if __name__ == "__main__":
    logger.warning("%s To start the app, use uvicorn cli with:", LOG_PREFIX)
    logger.warning("%s uv run uvicorn app.main:create_app --factory ...", LOG_PREFIX)
    config: Configuration = load_configuration()
    uvicorn.run(
        app="knowledge_flow_backend.main:create_app",
        factory=True,
        host=config.app.address,
        port=config.app.port,
        reload=config.app.reload,
        log_level=config.app.log_level.lower(),
    )
