#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

"""
Entrypoint for the knowledge_flow_app microservice.
"""

import argparse
import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from rich.logging import RichHandler

from app.application_context import ApplicationContext
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from app.features.content.controller import ContentController
from app.features.metadata.controller import MetadataController
from app.features.vector_search.controller import VectorSearchController
from app.features.tabular.controller import TabularController
from app.features.wip.ingestion_controller import IngestionController
from app.features.wip.knowledge_context_controller import KnowledgeContextController


# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

def configure_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=False, show_time=False, show_path=False)],
    )
    logging.getLogger().info(f"Logging configured at {log_level} level.")

configure_logging()

dotenv_path = os.getenv("ENV_FILE", "./config/.env")
if load_dotenv(dotenv_path):
    logging.getLogger().info(f"✅ Loaded environment variables from: {dotenv_path}")
else:
    logging.getLogger().warning(f"⚠️ No .env file found at: {dotenv_path}")


# -----------------------
# FASTAPI APP + ROUTES
# -----------------------

def create_app(config_path: str = "./config/configuration.yaml", base_url: str = "/knowledge/v1") -> FastAPI:
    logger = logging.getLogger(__name__)
    logger.info(f"🛠️ create_app() called with base_url={base_url}")
    configuration: Configuration = parse_server_configuration(config_path)
    ApplicationContext(configuration)

    app = FastAPI(
        docs_url=f"{base_url}/docs",
        redoc_url=f"{base_url}/redoc",
        openapi_url=f"{base_url}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.security.authorized_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    router = APIRouter()
    IngestionController(router)
    VectorSearchController(router)
    MetadataController(router)
    ContentController(router)
    KnowledgeContextController(router)
    TabularController(router)

    logger.info("🧩 All controllers registered.")
    app.include_router(router, prefix=base_url)

    return app

# Global ASGI app instance (used by both CLI and uvicorn)
app = create_app()

mcp = FastApiMCP(
    app,
    name="Knowledge Flow MCP",
    description="MCP server for Knowledge Flow",
    include_tags=["Vector Search", "Tabular"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount()


# -----------------------
# CLI MODE
# -----------------------

def parse_cli_opts():
    parser = argparse.ArgumentParser(description="Start the knowledge_flow_app microservice")
    parser.add_argument("--config-path", dest="server_configuration_path", default="./config/configuration.yaml", help="Path to configuration YAML file")
    parser.add_argument("--base-url", dest="server_base_url_path", default="/knowledge-flow/v1", help="Base path for all API endpoints")
    parser.add_argument("--server-address", dest="server_address", default="127.0.0.1", help="Server binding address")
    parser.add_argument("--server-port", dest="server_port", type=int, default=8111, help="Server port")
    parser.add_argument("--log-level", dest="server_log_level", default="info", help="Logging level")
    parser.add_argument("--server.reload", dest="server_reload", action="store_true", help="Enable auto-reload (for dev only)")
    parser.add_argument("--server.reloadDir", dest="server_reload_dir", type=str, default=".", help="Watch for changes in these directories")
    return parser.parse_args()

def main():
    args = parse_cli_opts()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.server_address,
        port=args.server_port,
        log_level=args.server_log_level,
        reload=args.server_reload,
        reload_dirs=args.server_reload_dir,
    )

if __name__ == "__main__":
    main()
