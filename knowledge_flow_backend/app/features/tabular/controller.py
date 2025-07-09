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

from app.features.tabular.service import TabularService
from app.features.tabular.structures import (
    TabularDatasetMetadata,
    TabularQueryRequest,
    TabularQueryResponse,
    TabularSchemaResponse,
)

logger = logging.getLogger(__name__)


class TabularController:
    """
    Controller for interacting with SQL-like tabular datasets
    stored in DuckDB within the Knowledge Flow system.

    Exposes endpoints to:
      - Retrieve the schema (columns and types) of a table
      - Query rows using SQL-like filters
      - List all registered tabular datasets

    This controller is exposed as an MCP tool, enabling agentic
    workflows over structured tabular data stored in DuckDB.
    """

    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tabular/{document_uid}/schema",
            response_model=TabularSchemaResponse,
            tags=["Tabular"],
            summary="Get schema for a tabular (CSV) document",
            operation_id="get_tabular_schema"
        )
        async def get_schema(document_uid: str):
            logger.info(f"Received schema request for table UID: {document_uid}")
            try:
                return self.service.get_schema(document_uid)
            except FileNotFoundError:
                logger.warning(f"Table not found for UID: {document_uid}")
                raise HTTPException(status_code=404, detail="Table not found")
            except Exception as e:
                logger.exception(f"Error fetching schema for UID {document_uid}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.post(
            "/tabular/{document_uid}/query",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            summary="Query rows from a tabular (CSV) document",
            operation_id="query_tabular_data"
        )
        async def query_tabular(document_uid: str, query: TabularQueryRequest):
            logger.info(f"Received query for table UID: {document_uid} with parameters: {query}")
            try:
                return self.service.query(document_uid, query)
            except FileNotFoundError:
                logger.warning(f"Table not found for UID: {document_uid}")
                raise HTTPException(status_code=404, detail="Table not found")
            except Exception as e:
                logger.exception(f"Error querying table for UID {document_uid}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.get(
            "/tabular/list",
            response_model=List[TabularDatasetMetadata],
            tags=["Tabular"],
            summary="List available tabular datasets (CSV)",
            operation_id="list_tabular_datasets"
        )
        async def list_tabular_datasets():
            logger.info("Received request to list all tabular datasets")
            try:
                return self.service.list_tabular_datasets()
            except Exception as e:
                logger.exception(f"Error listing tabular datasets: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
