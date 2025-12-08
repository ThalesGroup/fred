# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, Dict, List

from fred_core import Action, KeycloakUser, Resource, authorize
from fred_core.store.structures import StoreInfo

from knowledge_flow_backend.features.tabular.structures import (
    DTypes,
    GetSchemaResponse,
    ListTablesResponse,
    RawSQLResponse,
    TabularColumnSchema,
)
from knowledge_flow_backend.features.tabular.utils import check_read_query, check_write_query

logger = logging.getLogger(__name__)


class TabularService:
    """
    Service pour la gestion tabulaire multi-base.

    Désormais, un store doit être explicitement chargé via `load_store(db_name)`
    avant d'exécuter des opérations. Si aucun store n'est chargé, les méthodes
    lèvent une erreur invitant à appeler `load_store()` d'abord.
    """

    def __init__(self, stores_info: Dict[str, StoreInfo]):
        self.stores_info = stores_info

    def _check_write_allowed(self, db_name: str):
        store_info = self.stores_info.get(db_name)
        if store_info and store_info.mode != "read_and_write":
            raise PermissionError(f"Write operations are not allowed on database '{db_name}'")

    def _sanitize_table_name(self, name: str) -> str:
        return name.replace("-", "_")

    def _map_sql_type_to_literal(self, duckdb_type: str) -> DTypes:
        duckdb_type = duckdb_type.lower()
        if any(x in duckdb_type for x in ["varchar", "string", "text"]):
            return "string"
        if "boolean" in duckdb_type:
            return "boolean"
        if any(x in duckdb_type for x in ["timestamp", "date", "time"]):
            return "datetime"
        if any(x in duckdb_type for x in ["double", "real", "float"]):
            return "float"
        if "int" in duckdb_type:
            return "integer"
        return "unknown"

    # -------------------------------------------------------------------------
    # Main functions
    # -------------------------------------------------------------------------

    @authorize(action=Action.READ, resource=Resource.TABLES_DATABASES)
    def list_databases(self, user: KeycloakUser) -> List[str]:
        return list(self.stores_info.keys())

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def describe_table(self, user: KeycloakUser, db_name: str, table_name: str) -> GetSchemaResponse:
        store = self.stores_info[db_name].store
        table_name = self._sanitize_table_name(table_name)
        schema = store.get_table_schema(table_name)
        columns = [TabularColumnSchema(name=col, dtype=self._map_sql_type_to_literal(dtype)) for col, dtype in schema]
        count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table_name}"')
        row_count = int(count_df["count"].iloc[0])
        return GetSchemaResponse(db_name=db_name, table_name=table_name, columns=columns, row_count=row_count)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables(self, user: KeycloakUser, db_name: str) -> ListTablesResponse:
        store = self.stores_info[db_name].store
        table_names = store.list_tables()
        return ListTablesResponse(db_name=db_name, tables=table_names)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables_with_schema(self, user: KeycloakUser, db_name: str) -> List[GetSchemaResponse]:
        store = self.stores_info[db_name].store
        responses = []
        table_names = store.list_tables()
        for table in table_names:
            try:
                schema_info = store.get_table_schema(table)
                columns = [TabularColumnSchema(name=col_name, dtype=self._map_sql_type_to_literal(col_type)) for col_name, col_type in schema_info]
                count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table}"')
                row_count = int(count_df["count"].iloc[0])
                responses.append(
                    GetSchemaResponse(
                        db_name=db_name,
                        table_name=table,
                        columns=columns,
                        row_count=row_count,
                    )
                )
            except Exception as e:
                logger.warning(f"[{db_name}] Failed to load schema for {table}: {e}")
                continue
        return responses

    def get_context(self, user: KeycloakUser) -> Dict[str, Any]:
        """
        Returns the context of all databases and tables with schema info.
        This can be used by LLM agents to understand the available datasets.
        """
        context = {}
        try:
            databases = self.list_databases(user)
            for db_name in databases:
                n_tables = len(self.list_tables(user, db_name).tables)
                tables_info = self.list_tables_with_schema(user, db_name)
                context[db_name] = []
                for table in tables_info:
                    table_info = {
                        "table_name": table.table_name,
                        "columns": [{"name": col.name, "dtype": col.dtype} for col in table.columns] if n_tables < 5 else len(table.columns),
                        "row_count": table.row_count,
                    }
                    context[db_name].append(table_info)
        except Exception as e:
            logger.warning(f"Failed to get context: {e}")
        return context

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def query_read(self, user: KeycloakUser, db_name: str, query: str) -> RawSQLResponse:
        sql = query.strip().lower()
        sql = check_read_query(sql)
        store = self.stores_info[db_name].store
        df = store.execute_sql_query(query)

        return RawSQLResponse(
            db_name=db_name,
            sql_query=query,
            rows=df.to_dict(orient="records"),
            error=None,
        )

    # -------------------------------------------------------------------------
    # "read_and_write" functions
    # -------------------------------------------------------------------------

    @authorize(action=Action.UPDATE, resource=Resource.TABLES)
    @authorize(action=Action.CREATE, resource=Resource.TABLES)
    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def query_write(self, user: KeycloakUser, db_name: str, query: str) -> RawSQLResponse:
        sql = query.strip()
        if not sql:
            raise ValueError("Empty SQL string provided")
        store = self.stores_info[db_name].store
        self._check_write_allowed(db_name)
        sql = check_write_query(sql)
        store.execute_update_query(sql)
        return RawSQLResponse(db_name=db_name, sql_query=sql, rows=[], error=None)

    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def delete_table(self, user: KeycloakUser, db_name: str, table_name: str) -> None:
        self._check_write_allowed(db_name)
        try:
            store = self.stores_info[db_name].store
            store.delete_table(table_name)
            logger.info(f"Table '{table_name}' deleted from database '{db_name}'")
        except Exception as e:
            logger.error(f"Failed to delete table '{table_name}' from '{db_name}': {e}")
            raise
