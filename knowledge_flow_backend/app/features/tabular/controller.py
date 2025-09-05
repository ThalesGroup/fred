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
from fred_core import KeycloakUser, get_current_user

from app.application_context import ApplicationContext
from app.features.tabular.service import TabularService
from app.features.tabular.structures import RawSQLRequest, TabularQueryResponse, TabularSchemaResponse

logger = logging.getLogger(__name__)


class TabularController:
    """
    API controller to expose tabular tools (read and write) for multiple databases.
    """

    def __init__(self, router: APIRouter):
        self.context = ApplicationContext.get_instance()
        stores = self.context.get_tabular_stores()
        self.service = TabularService(stores)
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/tabular/databases", response_model=List[str], tags=["Tabular"], summary="List available databases", operation_id="list_tabular_databases")
        async def list_databases(_: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.list_databases()
            except Exception as e:
                logger.exception("Failed to list databases")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get("/tabular/{db_name}/tables", response_model=List[str], tags=["Tabular"], summary="List tables in a database", operation_id="list_table_names")
        async def list_tables(db_name: str = Path(..., description="Name of the tabular database"), _: KeycloakUser = Depends(get_current_user)):
            try:
                store = self.service._get_store(db_name)
                return store.list_tables()
            except Exception as e:
                logger.exception(f"Failed to list tables for {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        @router.get("/tabular/{db_name}/schemas", response_model=List[TabularSchemaResponse], tags=["Tabular"], summary="Get schemas of all tables in a database", operation_id="get_all_schemas")
        async def get_schemas(db_name: str = Path(..., description="Name of the tabular database"), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.list_tables_with_schema(db_name=db_name)
            except Exception as e:
                logger.exception(f"Failed to get schemas for {db_name}")
                raise HTTPException(status_code=500, detail=str(e))

        @router.post(
            "/tabular/{db_name}/sql",
            response_model=TabularQueryResponse,
            tags=["Tabular"],
            summary="Execute raw SQL query in a database",
            operation_id="raw_sql_query",
            description="Submit a raw SQL string. Use with caution: query is executed directly.",
        )
        async def raw_sql_query(db_name: str = Path(..., description="Name of the tabular database"), request: RawSQLRequest = Body(...), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.query(db_name=db_name, document_name="raw_sql", request=request)
            except PermissionError as e:
                logger.warning(f"[{db_name}] Forbidden SQL query attempt: {e}")
                raise HTTPException(status_code=403, detail=str(e))
            except Exception as e:
                logger.exception(f"[{db_name}] Raw SQL execution failed")
                raise HTTPException(status_code=500, detail=str(e))

        @router.delete("/tabular/{db_name}/tables/{table_name}", status_code=204, tags=["Tabular"], summary="Delete a table from a database", operation_id="delete_table")
        async def delete_table(
            db_name: str = Path(..., description="Name of the tabular database"), table_name: str = Path(..., description="Table name to delete"), _: KeycloakUser = Depends(get_current_user)
        ):
            try:
                self.service._check_write_allowed(db_name)

                if not table_name.isidentifier():
                    raise HTTPException(status_code=400, detail="Invalid table name")

                store = self.service._get_store(db_name)
                store.delete_table(table_name)
                logger.info(f"[{db_name}] Table '{table_name}' deleted successfully.")
            except PermissionError as pe:
                logger.warning(f"[{db_name}] Forbidden delete attempt: {pe}")
                raise HTTPException(status_code=403, detail=str(pe))
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            except Exception as e:
                logger.exception(f"[{db_name}] Failed to delete table '{table_name}'")
                raise HTTPException(status_code=500, detail=str(e))
