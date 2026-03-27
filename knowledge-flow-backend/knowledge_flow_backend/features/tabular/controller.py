import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fred_core import Action, KeycloakUser, OwnerFilter, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tag.structure import MissingTeamIdError
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
        def _raise_http_exception(exc: Exception) -> None:
            if isinstance(exc, PermissionError):
                raise HTTPException(status_code=403, detail=str(exc))
            if isinstance(exc, (ValueError, MissingTeamIdError)):
                raise HTTPException(status_code=400, detail=str(exc))
            raise HTTPException(status_code=500, detail=str(exc))

        @router.get(
            "/tabular/databases",
            response_model=List[str],
            tags=["Tabular"],
            summary="List available databases",
            operation_id="list_databases",
        )
        async def list_databases(
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES_DATABASES)
            try:
                return await self.service.list_databases(
                    user,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception("Failed to list databases")
                _raise_http_exception(e)
                raise

        @router.get(
            "/tabular/databases/{db_name}/tables",
            response_model=ListTablesResponse,
            tags=["Tabular"],
            summary="List tables in a given database",
            operation_id="list_tables",
        )
        async def list_tables(
            db_name: str = Path(..., description="Database name"),
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return await self.service.list_tables(
                    user,
                    db_name=db_name,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Failed to list tables for database {db_name}")
                _raise_http_exception(e)

        @router.get(
            "/tabular/databases/{db_name}/schemas",
            response_model=List[GetSchemaResponse],
            tags=["Tabular"],
            summary="List schemas of all tables in a given database",
            operation_id="get_database_schemas",
        )
        async def list_schemas(
            db_name: str = Path(..., description="Database name"),
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return await self.service.list_tables_with_schema(
                    user,
                    db_name=db_name,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Failed to list schemas for database {db_name}")
                raise _raise_http_exception(e)

        @router.get(
            "/tabular/databases/{db_name}/tables/{table_name}/descibe_table",
            response_model=GetSchemaResponse,
            tags=["Tabular"],
            summary="Get schema of a specific table",
            operation_id="describe_table",
        )
        async def describe_table(
            db_name: str = Path(..., description="Database name"),
            table_name: str = Path(..., description="Table name"),
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return await self.service.describe_table(
                    user,
                    db_name=db_name,
                    table_name=table_name,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Failed to get schema for {table_name} in database {db_name}")
                raise _raise_http_exception(e)

        @router.get(
            "/tabular/context",
            response_model=Dict[str, List[Dict[str, Any]]],
            tags=["Tabular"],
            summary="Return all databases with their tables",
            operation_id="get_context",
        )
        async def list_tabular_context(
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES_DATABASES)
            try:
                return await self.service.get_context(
                    user,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception("Failed to list databases and tables")
                raise _raise_http_exception(e)

        @router.post(
            "/tabular/databases/{db_name}/sql/read",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Execute a read-only SQL query on a given database (one statement allowed, DDL operations and dangerous SQL patterns are blocked)",
            operation_id="read_query",
        )
        async def raw_sql_read(
            db_name: str = Path(..., description="Database name"),
            request: RawSQLRequest = Body(..., description="SQL query payload"),
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return await self.service.query_read(
                    user,
                    db_name=db_name,
                    query=request.query,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Read SQL query failed on database {db_name}")
                _raise_http_exception(e)

        @router.post(
            "/tabular/databases/{db_name}/sql/write",
            response_model=RawSQLResponse,
            tags=["Tabular"],
            summary="Execute a write SQL query on a given database (one statement allowed and dangerous SQL patterns are blocked)",
            operation_id="execute_write_query",
        )
        async def raw_sql_write(
            db_name: str = Path(..., description="Database name"),
            request: RawSQLRequest = Body(..., description="SQL query payload"),
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.TABLES)
            try:
                return await self.service.query_write(
                    user,
                    db_name=db_name,
                    query=request.query,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Write SQL query failed on database {db_name}")
                _raise_http_exception(e)

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
            document_library_tags_ids: list[str] | None = Query(default=None, description="Optional library tag IDs to restrict visible tabular datasets."),
            owner_filter: OwnerFilter | None = Query(default=None, description="Filter by ownership: 'personal' or 'team'."),
            team_id: str | None = Query(default=None, description="Team ID, required when owner_filter is 'team'."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.TABLES)
            try:
                await self.service.delete_table(
                    user,
                    db_name=db_name,
                    table_name=table_name,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.exception(f"Failed to delete table {table_name} in database {db_name}")
                _raise_http_exception(e)
