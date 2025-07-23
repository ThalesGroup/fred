import logging
from typing import List, Optional
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
)

logger = logging.getLogger(__name__)


class TabularController:
    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tabular/full_metadata",
            response_model=List[TabularSchemaResponse],
            tags=["Tabular"],
            operation_id="list_all_with_schema",
            summary="List all tabular datasets with schema and row count"
        )
        async def list_all_with_schema():
            logger.info("Received request for full schema + metadata")
            try:
                return self.service.list_datasets_with_schema()
            except Exception as e:
                logger.exception(f"Error getting full tabular metadata: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")


        @router.post(
            "/tabular/howtomakeaquery",
            response_model=HowToMakeAQueryResponse,
            tags=["Tabular"],
            operation_id="how_to_make_query",
            summary="Give a documentation on how to make a query",
        )
        async def how_to_make_a_query():
            try:
                return self.service.how_to_make_a_query()
            except Exception as e:
                logger.exception("Error generating how-to query doc")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.post(
            "/tabular/{document_uid}/query",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            operation_id="make_query",
            summary="Execute a SQL-like query on a tabular dataset",
        )
        async def query_tabular(document_uid: str, query: TabularQueryRequest):
            try:
                return self.service.query(document_uid, query)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Table not found")
            except Exception as e:
                logger.exception(f"Error querying table {document_uid}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.get(
            "/tabular/{table_name}/aggregate",
            tags=["Tabular"],
            operation_id="aggregate_metrics_summary",
            summary="Aggregate numerical metrics over time or globally from a SQL table"
        )
        async def aggregate_tabular_metrics(
            table_name: str,
            start: Optional[str] = Query(default=None, description="Start time (ISO 8601)"),
            end: Optional[str] = Query(default=None, description="End time (ISO 8601)"),
            precision: Precision = Query(default=Precision.hour),
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[]),
            timestamp_column: str = Query(default="date", description="Timestamp column name")
        ):
            logger.info(f"Aggregation request on {table_name}, precision={precision}, groupby={groupby}")

            valid_ops = {"avg", "AVG", "sum", "SUM", "min", "MIN", "max", "MAX", "count", "COUNT", "COUNT DISTINCT", "count distinct"}
            agg_mapping = {}

            for item in agg:
                try:
                    field, op = item.split(":")
                    if op not in valid_ops:
                        raise HTTPException(status_code=400, detail=f"Invalid aggregation operation: '{op}'")
                    agg_mapping[field] = op
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid agg format: '{item}' (expected field:op)")

            try:
                start_dt = datetime.fromisoformat(start) if start else None
                end_dt = datetime.fromisoformat(end) if end else None
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")

            try:
                return self.service.get_aggregated_metrics_or_global(
                    table=table_name,
                    start=start_dt,
                    end=end_dt,
                    precision=precision,
                    agg_mapping=agg_mapping,
                    groupby_fields=groupby,
                    timestamp_column=timestamp_column
                )
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            except Exception as e:
                logger.exception(f"Aggregation failed on table {table_name}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
