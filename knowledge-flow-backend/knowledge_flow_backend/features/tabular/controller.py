import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import (
    GetSchemaResponse,
    ListTablesResponse,
    RawSQLRequest,
    RawSQLResponse,
)

logger = logging.getLogger(__name__)


class TabularController:
    """API controller for tabular operations on multiple databases."""

    def __init__(self, router: APIRouter):
        self.context = ApplicationContext.get_instance()
        stores = self.context.get_tabular_stores()
        self.service = TabularService(stores)
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        # -----------------------------
        # GET TABULAR CONTEXT
        # -----------------------------

        @router.get(
            "/tabular/context",
            response_model=List[Dict[str, Any]],
            tags=["Tabular"],
            summary="Return all databases with their tables",
            operation_id="get_context",
        )
        async def list_tabular_context(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.TABLES_DATABASES)
            try:
                return self.service.list_databases_with_tables(user)
            except Exception as e:
                logger.exception("Failed to list databases and tables")
                raise HTTPException(status_code=500, detail=str(e))

        # -----------------------------
        # DATABASE MANAGEMENT
        # -----------------------------

        @router.get(
            "/tabular/databases",
            response_model=List[str],
            tags=["Tabular"],
            summary="List available databases",
            operation_id="list_databases",
        )
        async def list_databases(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.TABLES_DATABASES)
            try:
                return self.service.list_databases(user)
            except Exception as e:
                logger.exception("Failed to list databases")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/databases/{db_name}/tables",
            response_model=ListTablesResponse,
            tags=["Tabular"],
            summary="List tables in a given database",
            operation_id="list_tables",
        )
        async def list_tables(
            db_name: str = Path(..., description="Database name"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.list_tables(user, db_name=db_name)
            except Exception as e:
                logger.exception(f"Failed to list tables for database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/databases/{db_name}/schemas",
            response_model=List[GetSchemaResponse],
            tags=["Tabular"],
            summary="List schemas of all tables in a given database",
            operation_id="get_database_schemas",
        )
        async def list_schemas(
            db_name: str = Path(..., description="Database name"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.list_tables_with_schema(user, db_name=db_name)
            except Exception as e:
                logger.exception(f"Failed to list schemas for database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/databases/{db_name}/tables/{table_name}/schema",
            response_model=GetSchemaResponse,
            tags=["Tabular"],
            summary="Get schema of a specific table",
            operation_id="get_schema",
        )
        async def get_table_schema(
            db_name: str = Path(..., description="Database name"),
            table_name: str = Path(..., description="Table name"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.get_schema(user, db_name=db_name, table_name=table_name)
            except Exception as e:
                logger.exception(f"Failed to get schema for {table_name} in database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        # -----------------------------
        # SQL QUERIES
        # -----------------------------

        @router.post(
            "/tabular/databases/{db_name}/sql/read",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Execute a read-only SQL query on a given database",
            operation_id="read_query",
        )
        async def raw_sql_read(
            db_name: str = Path(..., description="Database name"),
            request: RawSQLRequest = Body(..., description="SQL query payload"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.query_read(user, db_name=db_name, query=request.query)
            except Exception as e:
                logger.exception(f"Read SQL query failed on database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/databases/{db_name}/sql/write",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Execute a write SQL query on a given database",
            operation_id="write_query",
        )
        async def raw_sql_write(
            db_name: str = Path(..., description="Database name"),
            request: RawSQLRequest = Body(..., description="SQL query payload"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.TABLES)
            try:
                return self.service.query_write(user, db_name=db_name, query=request.query)
            except PermissionError as e:
                logger.warning(f"Write attempt forbidden on database {db_name}: {e}")
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.exception(f"Write SQL query failed on database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        # -----------------------------
        # DELETE TABLE
        # -----------------------------

        @router.delete(
            "/tabular/databases/{db_name}/tables/{table_name}",
            status_code=204,
            tags=["Tabular"],
            summary="Delete a table from a given database",
            operation_id="delete_table",
        )
        async def delete_table(
            db_name: str = Path(..., description="Database name"),
            table_name: str = Path(..., description="Table name"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.TABLES)
            try:
                self.service.delete_table(user, db_name=db_name, table_name=table_name)
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.exception(f"Failed to delete table {table_name} in database {db_name}")
                raise HTTPException(status_code=500, detail=str(e))
