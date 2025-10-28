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

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import (
    ListTableResponse,
    RawSQLRequest,
    TabularQueryResponse,
    TabularSchemaResponse,
)

logger = logging.getLogger(__name__)


class TabularController:
    """
    API controller exposing tabular operations for multiple databases.
    The controller now supports explicit database loading before operations.
    """

    def __init__(self, router: APIRouter):
        self.context = ApplicationContext.get_instance()
        stores = self.context.get_tabular_stores()
        self.service = TabularService(stores)
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        # -------------------------------------------------------------
        # DATABASE MANAGEMENT
        # -------------------------------------------------------------

        @router.get(
            "/tabular/databases",
            response_model=List[str],
            tags=["Tabular"],
            summary="List available databases",
            operation_id="list_tabular_databases",
        )
        async def list_databases(user: KeycloakUser = Depends(get_current_user)):
            """Return all available database names."""
            try:
                return self.service.list_databases(user)
            except Exception as e:
                logger.exception("Failed to list databases")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/load/{db_name}",
            tags=["Tabular"],
            summary="Load a specific database to be used in subsequent operations",
            operation_id="load_tabular_database",
        )
        async def load_database(
            db_name: str = Path(..., description="Name of the database to load"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """Explicitly load the database to be used for next queries."""
            authorize_or_raise(user, Action.READ, Resource.TABLES_DATABASES)
            try:
                self.service.load_store(db_name)
                return {"status": "ok", "loaded_db": db_name}
            except ValueError as e:
                logger.warning(f"Failed to load database '{db_name}': {e}")
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.exception(f"Unexpected error while loading database '{db_name}', error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # -------------------------------------------------------------
        # TABLE OPERATIONS
        # -------------------------------------------------------------

        @router.get(
            "/tabular/tables",
            response_model=ListTableResponse,
            tags=["Tabular"],
            summary="List tables in the loaded database",
            operation_id="list_tables_loaded_db",
        )
        async def list_tables(user: KeycloakUser = Depends(get_current_user)):
            """List all tables in the currently loaded database."""
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.list_tables(user)
            except RuntimeError as e:
                logger.warning(f"No database loaded: {e}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception("Failed to list tables")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/schemas",
            response_model=List[TabularSchemaResponse],
            tags=["Tabular"],
            summary="List schemas of all tables in the loaded database",
            operation_id="list_all_table_schemas_loaded_db",
        )
        async def get_all_schemas(user: KeycloakUser = Depends(get_current_user)):
            """Return schemas for all tables in the currently loaded database."""
            try:
                return self.service.list_tables_with_schema(user)
            except RuntimeError as e:
                logger.warning(f"No database loaded: {e}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception("Failed to retrieve schemas")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get(
            "/tabular/tables/{table_name}/schema",
            response_model=TabularSchemaResponse,
            tags=["Tabular"],
            summary="Get schema of a specific table in the loaded database",
            operation_id="get_table_schema_loaded_db",
        )
        async def get_table_schema(
            table_name: str = Path(..., description="Name of the table"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.TABLES)
            try:
                return self.service.get_schema(user, table_name)
            except RuntimeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception(f"Failed to get schema for {table_name}")
                raise HTTPException(status_code=500, detail=str(e))

        # -------------------------------------------------------------
        # SQL QUERIES
        # -------------------------------------------------------------

        @router.post(
            "/tabular/sql/read",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            summary="Execute a read-only SQL query on the loaded database",
            operation_id="tabular_sql_read_loaded_db",
        )
        async def raw_sql_read(
            request: RawSQLRequest = Body(...),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                return self.service.query_read(user, request=request)
            except RuntimeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception("Read SQL query failed")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/sql/write",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            summary="Execute a write SQL query on the loaded database",
            operation_id="tabular_sql_write_loaded_db",
        )
        async def raw_sql_write(
            request: RawSQLRequest = Body(...),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                return self.service.query_write(user, request=request)
            except PermissionError as e:
                logger.warning(f"Write attempt forbidden: {e}")
                raise HTTPException(status_code=403, detail=str(e))
            except RuntimeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception("Write SQL query failed")
                raise HTTPException(status_code=500, detail=str(e))

        # -------------------------------------------------------------
        # DELETE TABLE
        # -------------------------------------------------------------

        @router.delete(
            "/tabular/tables/{table_name}",
            status_code=204,
            tags=["Tabular"],
            summary="Delete a table from the loaded database",
            operation_id="delete_table_loaded_db",
        )
        async def delete_table(
            table_name: str = Path(..., description="Table name to delete"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.DELETE, Resource.TABLES)
            try:
                if not table_name.isidentifier():
                    raise HTTPException(status_code=400, detail="Invalid table name")
                self.service.delete_table(user=user, table_name=table_name)
                logger.info(f"Table '{table_name}' deleted successfully.")
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))
            except RuntimeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no_database_loaded",
                        "message": str(e),
                        "available_databases": self.service.list_databases(user),
                    },
                )
            except Exception as e:
                logger.exception(f"Failed to delete table '{table_name}'")
                raise HTTPException(status_code=500, detail=str(e))
