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

import logging
from typing import List
from fastapi import APIRouter, HTTPException

from knowledge_flow_app.features.tabular.service import TabularService
from knowledge_flow_app.features.tabular.structures import TabularDatasetMetadata, TabularQueryRequest, TabularQueryResponse, TabularSchemaResponse

logger = logging.getLogger(__name__)

class TabularController:
    """
    Controller responsible for interacting with tabular (CSV) datasets within the knowledge ingestion system.

    This controller exposes three core endpoints to:
      - Retrieve the **schema** (columns and types) of a CSV document
      - **Query** rows dynamically via a structured query interface
      - **List** all tabular datasets registered in the system

    Exposure:
    ---------
    This controller is **exposed as an MCP tool** via `main.py`, allowing agents to
    programmatically discover and interact with tabular datasets. It supports:
      - schema inspection (`/mcp/tabular/{uid}/schema`)
      - structured row queries (`/mcp/tabular/{uid}/query`)
      - available dataset enumeration (`/mcp/tabular/list`)

    Role and Positioning:
    ---------------------
    Serves as the access layer for **structured tabular data** ingested through Knowledge Flow,
    enabling downstream tools, agents (like Dominic), and user interfaces to:
      - Understand dataset shape and column semantics
      - Execute structured queries over tabular documents
      - Discover datasets tagged and indexed within the system

    Roadmap and Design Intent:
    --------------------------
    The current implementation is optimized for local CSV-backed datasets.
    Planned improvements include:
      - Semantic tagging and filtering of datasets
      - Schema enhancement (e.g., column types, missing value stats)
      - Backend flexibility (parquet, database, remote URLs)
      - Pagination, sorting, and value previewing

    This controller is **foundational** to building agentic workflows grounded
    in structured tabular knowledge and supports both REST and MCP use cases.
    """


    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tabular/{document_uid}/schema",
            response_model=TabularSchemaResponse,
            tags=["Tabular"],
            summary="Get schema for a tabular (CSV) document"
        )
        async def get_schema(document_uid: str):
            try:
                return self.service.get_schema(document_uid)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="CSV file not found")
            except Exception:
                logger.exception("Error fetching schema")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.post(
            "/tabular/{document_uid}/query",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            summary="Query rows from a tabular (CSV) document"
        )
        async def query_tabular(document_uid: str, query: TabularQueryRequest):
            try:
                return self.service.query(document_uid, query)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="CSV file not found")
            except Exception:
                logger.exception("Error querying tabular data")
                raise HTTPException(status_code=500, detail="Internal server error")
            
        @router.get(
            "/tabular/list",
            response_model=List[TabularDatasetMetadata],
            tags=["Tabular"],
            summary="List available tabular datasets (CSV)"
        )
        async def list_tabular_datasets():
            try:
                return self.service.list_tabular_datasets()
            except Exception:
                logger.exception("Error listing tabular datasets")
                raise HTTPException(status_code=500, detail="Internal server error")
