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
import time
import httpx

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


# --- QUICK HACK: service-auth for MCP API tools (Knowledge -> Knowledge) -------

def _split_realm_url(keycloak_url: str) -> tuple[str, str]:
    """
    Fred rationale:
    - Security config gives us a realm URL like: https://kc/auth/realms/<realm>
    - We need (keycloak_base, realm) to build the token endpoint for client-credentials.
    """
    parts = keycloak_url.strip("/").split("/")
    if "realms" not in parts:
        raise ValueError(f"Invalid keycloak_url (no /realms/): {keycloak_url}")
    i = parts.index("realms")
    keycloak_base = "/".join(parts[:i])  # e.g. https://kc/auth
    realm = parts[i + 1]
    return keycloak_base, realm


class _ClientCredentialsProvider:
    """
    Fred rationale:
    - MCP tools **inside Knowledge** call our own HTTP API (/knowledge-flow/v1/os/*).
    - Those calls must use a **service identity** (client-credentials), not a user token.
    - We cache the token and refresh just-in-time, or force-refresh on 401.
    """
    def __init__(self, keycloak_base: str, realm: str, client_id: str, secret_env: str):
        self.token_url = f"{keycloak_base}/realms/{realm}/protocol/openid-connect/token"
        self.client_id = client_id
        self.client_secret = os.getenv(secret_env) or ""
        if not self.client_secret:
            raise RuntimeError(
                f"Missing service client secret env '{secret_env}' for Knowledge MCP."
            )
        self._access_token = None
        self._exp_ts = 0.0
        self._leeway = 30  # seconds

    async def get(self, force: bool = False) -> str:
        now = time.time()
        if (not force) and self._access_token and now < (self._exp_ts - self._leeway):
            return self._access_token
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                self.token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
        r.raise_for_status()
        data = r.json()
        self._access_token = data["access_token"]
        self._exp_ts = now + float(data.get("expires_in", 300))
        return self._access_token


class _AsyncAutoRefreshBearer(httpx.Auth):
    """
    Fred rationale:
    - Attach service token to every outbound MCP API call.
    - If Keycloak returns 401 (token expired mid-flight), refresh & retry once.
    """
    def __init__(self, provider: _ClientCredentialsProvider):
        self.provider = provider

    async def async_auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {await self.provider.get()}"
        response = yield request
        if response.status_code == 401:
            request.headers["Authorization"] = f"Bearer {await self.provider.get(force=True)}"
            yield request  # single retry



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


    # --- QUICK HACK WIRING: give FastApiMCP a pre-auth'd httpx client ----------
    # We reuse Knowledge's security config but **use a dedicated service client**
    # for Knowledge itself. You already created this client in Keycloak and set
    # the secret in env: KEYCLOAK_KNOWLEDGE_TOKEN.
    keycloak_base, realm = _split_realm_url(configuration.app.security.keycloak_url)

    # IMPORTANT: this client_id is the **Knowledge service client**, not Agentic.
    knowledge_service_client_id = "knowledge"  # or a dedicated field if you have one
    knowledge_secret_env = "KEYCLOAK_KNOWLEDGE_TOKEN"

    _provider = _ClientCredentialsProvider(
        keycloak_base=keycloak_base,
        realm=realm,
        client_id=knowledge_service_client_id,
        secret_env=knowledge_secret_env,
    )
    _api_httpx = httpx.AsyncClient(timeout=15, auth=_AsyncAutoRefreshBearer(_provider))

    def _attach_api_httpx(mcp_obj):
        """
        Minimal, defensive way to inject our httpx client into fastapi_mcp.
        Different versions expose different hooks; we try common ones.
        """
        # 1) Preferred: constructor arg existed (future-proof) -> nothing to do
        # 2) Common attr:
        if hasattr(mcp_obj, "api_httpx_client"):
            mcp_obj.api_httpx_client = _api_httpx
            logger.warning("fastapi_mcp._client.api_httpx_client found, injecting.")
            return
        # 3) Method hook:
        if hasattr(mcp_obj, "set_api_httpx_client"):
            try:
                mcp_obj.set_api_httpx_client(_api_httpx)
                logger.warning("fastapi_mcp.set_api_httpx_client() found, injecting.")
                return
            except Exception:
                pass
        logger.error("Failed to attach API httpx client to FastApiMCP.")

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
    mcp_prefix = "/knowledge-flow/v1"
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
    _attach_api_httpx(mcp_opensearch_ops)
    mcp_opensearch_ops.mount(mount_path=f"{mcp_prefix}/mcp-opensearch-ops")

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
    _attach_api_httpx(mcp_kpi)
    mcp_kpi.mount(mount_path=f"{mcp_prefix}/mcp-kpi")

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
    _attach_api_httpx(mcp_tabular)
    mcp_tabular.mount(mount_path=f"{mcp_prefix}/mcp-tabular")

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
    _attach_api_httpx(mcp_text)
    mcp_text.mount(mount_path=f"{mcp_prefix}/mcp-text")

    mcp_template = FastApiMCP(
        app,
        name="Knowledge Flow Text MCP",
        description="MCP server for Knowledge Flow Text",
        include_tags=["Templates", "Prompts"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    _attach_api_httpx(mcp_template)
    mcp_template.mount(mount_path=f"{mcp_prefix}/mcp-template")

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
    _attach_api_httpx(mcp_code)
    mcp_code.mount(mount_path=f"{mcp_prefix}/mcp-code")

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
    _attach_api_httpx(mcp_resources)
    mcp_resources.mount(mount_path=f"{mcp_prefix}/mcp-resources")

    return app


# -----------------------
# MAIN ENTRYPOINT
# -----------------------

if __name__ == "__main__":
    print("To start the app, use uvicorn cli with:")
    print("uv run uvicorn --factory app.main:create_app ...")
