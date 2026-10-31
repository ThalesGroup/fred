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

"""
Knowledge Flow API: the backend of agent capabilities on Weaver.

Agent pods call it for one person inside an admitted turn. It mounts only the
endpoints adapted to Weaver spaces; the document drive belongs to Control Plane.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import APIRouter, Depends, FastAPI
from fred_core import initialize_user_security, log_setup
from fred_core.common import read_env_bool, register_exception_handlers
from fred_core.diagnostics import install_gc_diagnostics
from fred_core.kpi import KPIMiddleware, emit_process_kpis, emit_sql_pool_kpis
from fred_core.logs.http import RequestLoggingFastAPI
from fred_core.logs.null_log_store import NullLogStore
from fred_core.security.mcp_delegation import declare_delegation_parameters
from fred_core.security.oidc import configure_token_security
from prometheus_client import start_http_server
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import load_configuration
from knowledge_flow_backend.common.structures import Configuration
from knowledge_flow_backend.core.monitoring.monitoring_controller import MonitoringController
from knowledge_flow_backend.features.content.published_markdown import MarkdownController
from knowledge_flow_backend.features.document_scope import declare_document_context_openapi
from knowledge_flow_backend.features.extract.controller import ExtractController
from knowledge_flow_backend.features.summarize.controller import SummarizeController
from knowledge_flow_backend.features.tabular.controller import TabularController
from knowledge_flow_backend.features.tabular.execution import close_tabular_execution, register_tabular_exception_handlers
from knowledge_flow_backend.features.vector_search.vector_search_controller import VectorSearchController
from knowledge_flow_backend.mcp_mount import mount_fastapi_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOG_PREFIX = "[APP]"


def create_app() -> FastAPI:
    configuration: Configuration = load_configuration()
    log_setup(
        service_name="knowledge-flow",
        log_level=configuration.app.log_level,
        log_format=configuration.app.log_format,
        service_role="api",
        store=NullLogStore(),
    )
    logger.info("%s Embedding model: [%s] %s", LOG_PREFIX, configuration.embedding_model.provider, configuration.embedding_model.name)

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
    application_context._log_config_summary()
    docs_enabled = read_env_bool("PRODUCTION_FASTAPI_DOCS_ENABLED", default=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        application_context.open_authorization_client()
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
        try:
            yield
        finally:
            for task in (process_kpi_task, db_pool_kpi_task):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            await gc_diagnostics.stop()
            close_tabular_execution()
            await application_context.shutdown()

    app = RequestLoggingFastAPI(
        docs_url=f"{configuration.app.base_url}/docs" if docs_enabled else None,
        redoc_url=f"{configuration.app.base_url}/redoc" if docs_enabled else None,
        openapi_url=f"{configuration.app.base_url}/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) behind a TLS-terminating ingress.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")  # type: ignore[arg-type]

    prom_cfg = configuration.observability.kpi.prometheus
    if prom_cfg.enabled:
        start_http_server(prom_cfg.port, addr=prom_cfg.address)

    register_exception_handlers(app)
    register_tabular_exception_handlers(app)
    initialize_user_security(configuration.security.user)
    # JWT and trusted delegation only; admission is Control Plane's, at turn start.
    configure_token_security(configuration.security)

    app.add_request_middleware(KPIMiddleware, kpi=application_context.get_kpi_writer)
    monitoring_router = APIRouter(prefix=configuration.app.base_url)
    router = APIRouter(
        prefix=configuration.app.base_url,
        dependencies=[Depends(declare_delegation_parameters)],
    )
    MonitoringController(monitoring_router, application_context)
    VectorSearchController(router)
    MarkdownController(router)
    SummarizeController(router)
    ExtractController(router)
    TabularController(router)
    app.include_router(monitoring_router)
    app.include_router(router)
    declare_document_context_openapi(app)
    mount_fastapi_tools(
        app,
        path=f"{configuration.app.base_url}/mcp/tabular",
        name="Knowledge Flow Tabular MCP",
        description="Query published CSV and Excel tables in the active document selection. Start with list_tabular_documents, then describe_tabular_documents, search_tabular_values or query_tabular_documents.",
        tags={"Tabular"},
    )
    return app


if __name__ == "__main__":
    config: Configuration = load_configuration()
    uvicorn.run(
        app="knowledge_flow_backend.main:create_app",
        factory=True,
        host=config.app.address,
        port=config.app.port,
        reload=config.app.reload,
        log_level=config.app.log_level.lower(),
    )
