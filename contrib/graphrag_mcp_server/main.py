# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GraphRAG Backend Minimal - Configuration entirely via .env
"""

import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from graph_search.controller import GraphNodeController

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOG_PREFIX = "[GRAPH-RAG]"

load_dotenv()  # Load all config from .env

APP_BASE_URL = os.getenv("APP_BASE_URL", "/graph-rag")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8080))
APP_RELOAD = os.getenv("APP_RELOAD", "False").lower() == "true"
LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO")

GPU_ENABLED = os.getenv("USE_GPU", "False").lower() == "true"

if not GPU_ENABLED:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["MPS_VISIBLE_DEVICES"] = ""
    import torch
    torch.set_default_device("cpu")
    logger.warning("%s GPU support is disabled. Running on CPU.", LOG_PREFIX)

# -----------------------
# APP CREATION
# -----------------------

def create_app() -> FastAPI:

    app = FastAPI(
        docs_url=f"{APP_BASE_URL}/docs",
        redoc_url=f"{APP_BASE_URL}/redoc",
        openapi_url=f"{APP_BASE_URL}/openapi.json",
    )

    # CORS
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------
    # GraphRAG Specific
    # -----------------------
    router = APIRouter(prefix=APP_BASE_URL)
    GraphNodeController(router)
    app.include_router(router)

    # MCP Graph
    mcp_graph = FastApiMCP(
        app,
        name="Knowledge Flow Graph Text MCP",
        description=(
            "Graph search interface using Neo4j. "
            "Perform graph-based queries over documents and retrieve grounded answers."
        ),
        include_tags=["GraphSearch"],
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp_graph.mount_http(mount_path=f"{APP_BASE_URL}/mcp-graph")
    logger.info("%s MCP Graph mounted at %s/mcp-graph", LOG_PREFIX, APP_BASE_URL)

    return app

# -----------------------
# MAIN ENTRYPOINT
# -----------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:create_app",
        factory=True,
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_RELOAD,
        log_level=LOG_LEVEL.lower(),
    )
