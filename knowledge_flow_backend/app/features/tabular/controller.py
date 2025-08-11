import logging
from typing import List

from fastapi import APIRouter, HTTPException

from app.features.tabular.service import TabularService
from app.features.tabular.structures import RawSQLRequest, TabularQueryResponse, TabularSchemaResponse
from app.features.tabular.utils import extract_safe_sql_query

logger = logging.getLogger(__name__)


class TabularController:
    """
    Lightweight API controller to expose tabular tools to LLM agents:
      - List available tables
      - Get full schema for each table
      - Execute a SQLQueryPlan
    """

    def __init__(self, router: APIRouter):
        self.service = TabularService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/tabular/tables", response_model=List[str], tags=["Tabular"], operation_id="list_table_names", summary="List all available table names")
        async def list_tables():
            logger.info("Listing all available table names")
            try:
                if self.service.tabular_store is None:
                    raise RuntimeError("tabular_store is not initialized")
                return self.service.tabular_store.list_tables()
            except Exception as e:
                logger.exception("Failed to list table names")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get("/tabular/schemas", response_model=List[TabularSchemaResponse], tags=["Tabular"], operation_id="get_all_schemas", summary="Get schemas for all available tables")
        async def get_schemas():
            logger.info("Fetching schemas for all datasets")
            try:
                return self.service.list_datasets_with_schema()
            except Exception as e:
                logger.exception("Failed to get schemas")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/sql",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            operation_id="raw_sql_query",
            summary="Execute raw SQL query directly",
            description="Submit a raw SQL string. Use this with caution: the query is executed directly.",
        )
        async def raw_sql_query(request: RawSQLRequest):
            try:
                sql = extract_safe_sql_query(request.query)
                logger.info(f"Executing raw SQL: {sql}")
                return self.service.query(document_name="raw_sql", request=RawSQLRequest(query=sql))

            except PermissionError as e:
                logger.warning(f"Forbidden SQL query attempt: {e}")
                raise HTTPException(status_code=403, detail=str(e))

            except Exception:
                logger.exception("Raw SQL execution failed")
                raise HTTPException(status_code=500, detail="Internal server error")
