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
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fred_core import enforce_account_status, get_config, initialize_user_security, log_setup
from fred_core.common import read_env_bool, register_exception_handlers
from fred_core.diagnostics import install_gc_diagnostics
from fred_core.kpi import KPIMiddleware, emit_process_kpis, emit_sql_pool_kpis
from fred_core.logs.http import REFERENCE_HEADERS, RequestLoggingFastAPI
from fred_core.logs.null_log_store import NullLogStore
from fred_core.scheduler import SchedulerBackend, TemporalClientProvider
from fred_core.security.mcp_delegation import (
    declare_delegation_parameters,
)
from fred_core.sql import require_tables
from prometheus_client import start_http_server
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.common.config_loader import (
    load_configuration,
)
from knowledge_flow_backend.common.structures import Configuration
from knowledge_flow_backend.core.monitoring.monitoring_controller import (
    MonitoringController,
)
from knowledge_flow_backend.features.audio.audio_transcription_controller import AudioTranscriptionController
from knowledge_flow_backend.features.content import report_controller
from knowledge_flow_backend.features.content.content_controller import ContentController
from knowledge_flow_backend.features.corpus_tree.controller import CorpusTreeController
from knowledge_flow_backend.features.extract.controller import ExtractController
from knowledge_flow_backend.features.filesystem.mcp_fs_controller import McpFilesystemController
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from knowledge_flow_backend.features.kpi.opensearch_controller import (
    OpenSearchOpsController,
)
from knowledge_flow_backend.features.kpi.prometheus_controller import (
    PrometheusOpsController,
)
from knowledge_flow_backend.features.library_sync.controller import LibrarySyncController
from knowledge_flow_backend.features.metadata.controller import MetadataController
from knowledge_flow_backend.features.resources.controller import ResourceController
from knowledge_flow_backend.features.scheduler.scheduler_controller import SchedulerController
from knowledge_flow_backend.features.summarize.controller import SummarizeController
from knowledge_flow_backend.features.tabular.controller import TabularController
from knowledge_flow_backend.features.tabular.execution import register_tabular_exception_handlers
from knowledge_flow_backend.features.tag.tag_controller import TagController
from knowledge_flow_backend.features.tasks.controller import TasksController
from knowledge_flow_backend.features.vector_search.vector_search_controller import (
    VectorSearchController,
)
from knowledge_flow_backend.mcp_mount import mount_fastapi_tools
from knowledge_flow_backend.models.table_ownership import REQUIRED_TABLES

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOG_PREFIX = "[APP]"


def _norm_origin(o) -> str:
    # Ensure exact match with browser's Origin header (no trailing slash)
    return str(o).rstrip("/")


# -----------------------
# APP CREATION
# -----------------------


def create_app() -> FastAPI:
    configuration: Configuration = load_configuration()
    log_setup(
        service_name="knowledge-flow",
        log_level=configuration.app.log_level,
        log_format=configuration.app.log_format,
        service_role="api",
        store=NullLogStore(),
    )
    logger.info("Application configuration ready")
    logger.info("%s Embedding model: [%s] %s", LOG_PREFIX, configuration.embedding_model.provider, configuration.embedding_model.name)
    logger.info("%s Chat model: [%s] %s", LOG_PREFIX, configuration.chat_model.provider, configuration.chat_model.name)
    if configuration.ocr_model:
        logger.info("%s OCR model: [%s] %s", LOG_PREFIX, configuration.ocr_model.provider, configuration.ocr_model.name)

    base_url = configuration.app.base_url

    if not configuration.processing.is_gpu_enabled_any_profile():
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["MPS_VISIBLE_DEVICES"] = ""
        import torch

        torch.set_default_device("cpu")
        logger.info("%s GPU support is disabled. Running on CPU.", LOG_PREFIX)

    application_context = ApplicationContext(configuration)
    log_setup(
        service_name="knowledge-flow",
        log_level=configuration.app.log_level,
        log_format=configuration.app.log_format,
        service_role="api",
        store=application_context.get_log_store(),
    )
    logger.info("%s create_app() called with base_url=%s", LOG_PREFIX, base_url)
    application_context._log_config_summary()
    docs_enabled = read_env_bool("PRODUCTION_FASTAPI_DOCS_ENABLED", default=True)
    logger.info("%s FastAPI docs/openapi endpoints enabled=%s", LOG_PREFIX, docs_enabled)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await enforce_account_status(application_context.get_rebac_engine())
        from fred_core.security.platform_access.access_control import initialize_platform_access, platform_access_available

        if platform_access_available(configuration.security):
            await initialize_platform_access(configuration.security, application_context.get_pg_async_engine(), application_context.get_rebac_engine())
        # #2314 (closes the #2313 defect): startup creates NO tables — DDL is
        # owned by the Alembic trees alone (see models/table_ownership.py and
        # DATABASE_MIGRATIONS.md §"Table ownership across trees"). A
        # deployment that skipped migration jobs must fail here, at boot,
        # with the fix command — not mid-request as an UndefinedTableError.
        await require_tables(
            application_context.get_pg_async_engine(),
            sorted(REQUIRED_TABLES),
            component="knowledge-flow",
            migrate_command="make db-upgrade (apps/knowledge-flow-backend)",
            version_table="alembic_version_knowledge_flow",
        )

        # SIGUSR1/SIGUSR2 manual triggers + optional periodic gc.collect()+
        # malloc_trim() mitigation (fred_core.diagnostics, ISSUE-010).
        gc_diagnostics = install_gc_diagnostics()

        process_kpi_task = None
        db_pool_kpi_task = None
        interval_s = float(configuration.observability.kpi.process_metrics_interval_sec)
        if interval_s > 0:
            process_kpi_task = asyncio.create_task(emit_process_kpis(interval_s, application_context.get_kpi_writer()))
            db_pool_kpi_task = asyncio.create_task(
                emit_sql_pool_kpis(
                    interval_s,
                    application_context.get_kpi_writer(),
                    application_context.get_pg_async_engine(),
                    pool_name="knowledge-flow-postgres",
                )
            )

        # OPS-04: periodically reconcile abandoned tasks (e.g. worker down past the
        # workflow timeout) against their executors so they never stay pending forever.
        task_sweeper_task = None
        try:
            _task_service = application_context.get_task_service()
        except Exception:
            logger.warning("OPS-04: task service unavailable — reconciliation sweeper disabled", exc_info=True)
            _task_service = None
        if _task_service is not None:
            from fred_core.tasks.service import run_reconcile_sweeper

            from knowledge_flow_backend.features.metadata.service import MetadataService
            from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService

            retry_submissions = None
            if configuration.scheduler.enabled:
                ingestion_scheduler = IngestionTaskService(
                    scheduler_config=configuration.scheduler,
                    processing_config=configuration.processing,
                    metadata_service=MetadataService(),
                    max_parallelism=configuration.scheduler.temporal.ingestion_workflow_parallelism,
                )
                retry_submissions = ingestion_scheduler.delivery().retry_pending
            task_sweeper_task = asyncio.create_task(run_reconcile_sweeper(_task_service, before_reconcile=retry_submissions))

        try:
            yield
        finally:
            if task_sweeper_task:
                task_sweeper_task.cancel()
                with suppress(asyncio.CancelledError):
                    await task_sweeper_task
            if process_kpi_task:
                process_kpi_task.cancel()
                with suppress(asyncio.CancelledError):
                    await process_kpi_task
            if db_pool_kpi_task:
                db_pool_kpi_task.cancel()
                with suppress(asyncio.CancelledError):
                    await db_pool_kpi_task
            await gc_diagnostics.stop()
            await application_context.shutdown()

    app = RequestLoggingFastAPI(
        docs_url=f"{configuration.app.base_url}/docs" if docs_enabled else None,
        redoc_url=f"{configuration.app.base_url}/redoc" if docs_enabled else None,
        openapi_url=f"{configuration.app.base_url}/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.dependency_overrides[get_config] = get_configuration

    # Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) so that
    # request.base_url uses https:// when behind a TLS-terminating ingress.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")  # type: ignore[arg-type]

    prom_cfg = configuration.observability.kpi.prometheus
    if prom_cfg.enabled:
        start_http_server(prom_cfg.port, addr=prom_cfg.address)

    # Register exception handlers
    register_exception_handlers(app)
    # The tabular execution guard is reached from several features (tabular
    # routes, document preview, summarize, corpus filesystem), so its two
    # errors are mapped once here rather than per route.
    register_tabular_exception_handlers(app)

    allowed_origins = list({_norm_origin(o) for o in configuration.security.authorized_origins})
    logger.info("%s[CORS] allow_origins=%s", LOG_PREFIX, allowed_origins)
    app.add_request_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=REFERENCE_HEADERS,
    )
    initialize_user_security(configuration.security.user)
    # Enforce the hardened security profile (C3) at startup — fails closed (RUNTIME-07
    # rev. 2). Knowledge-flow is a request authority (serves documents under ReBAC), so
    # under profile=c3 it must refuse to boot unless user + m2m + rebac are enabled.
    from fred_core.security.oidc import apply_security_profile

    apply_security_profile(configuration.security)

    app.add_request_middleware(KPIMiddleware, kpi=application_context.get_kpi_writer)
    monitoring_router = APIRouter(prefix=configuration.app.base_url)
    router = APIRouter(
        prefix=configuration.app.base_url,
        dependencies=[Depends(declare_delegation_parameters)],
    )

    MonitoringController(monitoring_router, application_context)

    # Register base controllers. These are the one always needed.
    TasksController(router)
    MetadataController(router)
    ContentController(router)
    AudioTranscriptionController(router)
    IngestionController(router)
    LibrarySyncController(router)
    TagController(app, router)
    VectorSearchController(router)
    CorpusTreeController(router)
    SummarizeController(app, router)
    ExtractController(app, router)
    ResourceController(router)
    McpFilesystemController(router)

    if configuration.mcp.tabular_enabled:
        # Required for Tessa
        TabularController(router)
        logger.info("%s TabularController registered (mcp.tabular_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s TabularController disabled via configuration.mcp.tabular_enabled=false", LOG_PREFIX)

    if configuration.mcp.opensearch_ops_enabled:
        OpenSearchOpsController(router)
        logger.info("%s OpenSearchOpsController registered (mcp.opensearch_ops_enabled=true)", LOG_PREFIX)
    else:
        logger.warning("%s OpenSearchOpsController disabled via configuration.mcp.opensearch_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.prometheus_ops_enabled:
        PrometheusOpsController(router)
        logger.info("%s PrometheusOpsController registered (mcp.prometheus_ops_enabled=true)", LOG_PREFIX)
    else:
        logger.info("%s PrometheusOpsController disabled via configuration.mcp.prometheus_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.reports_enabled:
        logger.info("%s ReportsController registered (mcp.reports_enabled=true)", LOG_PREFIX)
        router.include_router(report_controller.router)
    else:
        logger.warning("%s ReportsController disabled via configuration.mcp.reports_enabled=false", LOG_PREFIX)

    if configuration.scheduler.enabled:
        logger.info("%s Activating ingestion scheduler controller.", LOG_PREFIX)
        temporal_client_provider = None
        scheduler_backend = application_context.get_scheduler_backend()

        if scheduler_backend == SchedulerBackend.TEMPORAL:
            temporal_cfg = configuration.scheduler.temporal
            if not temporal_cfg:
                raise ValueError("Scheduler enabled with temporal backend but temporal configuration is missing!")
            if not temporal_cfg.task_queue:
                raise ValueError("Scheduler enabled but Temporal task_queue is not set in configuration!")
            temporal_client_provider = TemporalClientProvider(temporal_cfg)
        else:
            logger.info(
                "%s Standalone scheduler mode active (effective backend=%s).",
                LOG_PREFIX,
                scheduler_backend,
            )

        SchedulerController(router, temporal_client_provider=temporal_client_provider)
    else:
        logger.warning("%s Ingestion scheduler controller disabled via configuration.scheduler.enabled=false", LOG_PREFIX)

    logger.info("%s All controllers registered.", LOG_PREFIX)
    app.include_router(monitoring_router)
    app.include_router(router)
    mcp_prefix = "/knowledge-flow/v1"

    mount_fastapi_tools(
        app,
        path=f"{mcp_prefix}/mcp-reports",
        name="Knowledge Flow Reports MCP",
        description="Create Markdown-first reports and get downloadable artifacts.",
        tags={"Reports"},
    )

    if configuration.mcp.opensearch_ops_enabled:
        mcp_mount_path = f"{mcp_prefix}/mcp-opensearch-ops"
        mount_fastapi_tools(
            app,
            path=mcp_mount_path,
            name="Knowledge Flow OpenSearch Ops MCP",
            description="Read-only operational tools for OpenSearch: cluster health, nodes, shards, indices, mappings, and sample docs. Monitoring/diagnostics only.",
            tags={"OpenSearch"},
        )
        logger.info("%s MCP OpenSearch Ops mounted at %s", LOG_PREFIX, mcp_mount_path)
    else:
        logger.warning("%s MCP OpenSearch Ops disabled via configuration.mcp.opensearch_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.prometheus_ops_enabled:
        mcp_mount_path = f"{mcp_prefix}/mcp-prometheus-ops"
        mount_fastapi_tools(
            app,
            path=mcp_mount_path,
            name="Knowledge Flow Prometheus Ops MCP",
            description="Read-only Prometheus-compatible operational tools for cluster-wide metrics exploration, PromQL queries, and metric discovery across namespaces and pods.",
            tags={"Prometheus"},
        )
        logger.info("%s MCP Prometheus Ops mounted at %s", LOG_PREFIX, mcp_mount_path)
    else:
        logger.info("%s MCP Prometheus Ops disabled via configuration.mcp.prometheus_ops_enabled=false", LOG_PREFIX)

    if configuration.mcp.tabular_enabled:
        mount_fastapi_tools(
            app,
            path=f"{mcp_prefix}/mcp-tabular",
            name="Knowledge Flow Tabular MCP",
            description=(
                "Read-only SQL access to the tabular documents ingested in Knowledge Flow: "
                "CSV files (one table each) and Excel workbooks (one or several extracted tables), "
                "stored as Parquet and queried through DuckDB. "
                "Recommended flow: list_tabular_documents to discover document names and, for Excel, "
                "their tables with technical identifiers for follow-up calls; "
                "describe_tabular_documents for the spreadsheet extraction catalog first "
                "(sheet layout, table context and ranges, residual notes, exact SQL aliases), "
                "then the typed schemas of every requested CSV or spreadsheet table; "
                "read_query to run one read-only SELECT over the mounted tables. "
                "Always scope read_query with dataset_uids (document uids - one spreadsheet uid mounts "
                "every table of the workbook). No write operations are available."
            ),
            tags={"Tabular"},
        )
    else:
        logger.info("%s MCP Tabular disabled via configuration.mcp.tabular_enabled=false", LOG_PREFIX)

    if configuration.mcp.text_enabled:
        mount_fastapi_tools(
            app,
            path=f"{mcp_prefix}/mcp-text",
            name="Knowledge Flow Text MCP",
            description=(
                "Semantic text search interface backed by the vector store. "
                "Use this MCP to perform vector similarity search over ingested documents, "
                "retrieve relevant passages, and ground answers in source material. "
                "It supports queries by text embedding rather than keyword match."
            ),
            tags={"Vector Search"},
        )
    else:
        logger.info("%s MCP Text disabled via configuration.mcp.text_enabled=false", LOG_PREFIX)

    if configuration.mcp.templates_enabled:
        mount_fastapi_tools(
            app,
            path=f"{mcp_prefix}/mcp-template",
            name="Knowledge Flow Text MCP",
            description="MCP server for Knowledge Flow Text",
            tags={"Templates", "Prompts"},
        )
    else:
        logger.info("%s MCP Templates disabled via configuration.mcp.templates_enabled=false", LOG_PREFIX)

    if configuration.mcp.resources_enabled:
        mount_fastapi_tools(
            app,
            path=f"{mcp_prefix}/mcp-resources",
            name="Knowledge Flow Resources MCP",
            description=(
                "Access to reusable resources for agents. "
                "Provides prompts, templates, and other content assets that can be used "
                "to customize agent behavior or generate well-structured custom reports. "
                "Use this MCP to browse, retrieve, and apply predefined resources when composing answers or building workflows."
            ),
            tags={"Resources", "Tags"},
        )
    else:
        logger.info("%s MCP Resources disabled via configuration.mcp.resources_enabled=false", LOG_PREFIX)

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
