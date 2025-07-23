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
from typing import List, Annotated
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.features.tabular.service import TabularService
from app.features.tabular.structures import (
    TabularDatasetMetadata,
    TabularQueryRequest,
    TabularQueryResponse,
    TabularSchemaResponse,
    HowToMakeAQueryResponse,
    Precision,
    Aggregation
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
            operation_id="get_schema",
            summary="Get schema (columns/types) of a SQL-like table"
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
            "/tabular/howtomakeaquery",
            response_model=HowToMakeAQueryResponse,
            tags=["Tabular"],
            operation_id="how_to_make_query",
            summary="Give a documentation on how to make a query",
        )
        async def how_to_make_a_query():
            logger.info(f"Received query to have the query documentation")
            try:
                return self.service.how_to_make_a_query()
            except Exception as e:
                logger.warning(f"Error: {e}")


        @router.post(
            "/tabular/{document_uid}/query",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            operation_id="make_query",
            summary="Execute a SQL-like query on a tabular dataset",
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
            operation_id="list_tables",
            summary="List available SQL-like tabular datasets"
        )
        async def list_tabular_datasets():
            logger.info("Received request to list all tabular datasets")
            try:
                return self.service.list_tabular_datasets()
            except Exception as e:
                logger.exception(f"Error listing tabular datasets: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
            
        def str_to_bool(value: str) -> bool:
            return value.lower() in ("true", "1", "yes")
            
        @router.get(
            "/tabular/{table_name}/aggregate",
            tags=["Tabular"],
            operation_id="aggregate_metrics_summary",
            summary="Aggregate numerical metrics over time and return global summary"
        )
        async def aggregate_tabular_metrics(
            table_name: str,
            start: Annotated[str, Query(description="Start time (ISO 8601)")],
            end: Annotated[str, Query(description="End time (ISO 8601)")],
            precision: Precision = Query(default=Precision.hour),
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[]),
            timestamp_column: str = Query(default="date", description="Timestamp column name"),
            include_global: Annotated[bool, Query()] = False
        ):
            logger.info(f"Aggregation request on {table_name} from {start} to {end}")

            def parse_dates(start: str, end: str) -> (datetime, datetime):
                return datetime.fromisoformat(start), datetime.fromisoformat(end)

            VALID_OPS = {"avg", "AVG", "sum", "SUM", "min", "MIN", "max", "MAX", "count", "COUNT"}

            try:
                start_dt, end_dt = parse_dates(start, end)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")

            agg_mapping = {}
            for item in agg:
                try:
                    field, op = item.split(":")
                    if op not in VALID_OPS:
                        raise HTTPException(status_code=400, detail=f"Invalid aggregation operation: '{op}' (allowed: {VALID_OPS})")
                    agg_mapping[field] = op
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid agg format: '{item}' (expected field:op)")

            try:
                return self.service.get_aggregated_metrics_with_summary(
                    table=table_name,
                    start=start_dt,
                    end=end_dt,
                    precision=precision,
                    agg_mapping=agg_mapping,
                    groupby_fields=groupby,
                    timestamp_column=timestamp_column,
                    include_global=include_global
                )
            except Exception as e:
                logger.exception(f"Error aggregating table {table_name}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

