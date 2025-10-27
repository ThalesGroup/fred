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
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fred_core import Action, KeycloakUser, Resource, authorize
from fred_core.store.sql_store import SQLTableStore
from fred_core.store.structures import StoreInfo

from knowledge_flow_backend.features.tabular.structures import (
    DTypes,
    RawSQLRequest,
    TabularColumnSchema,
    ListTableResponse,
    TabularQueryResponse,
    TabularSchemaResponse,
)

logger = logging.getLogger(__name__)


class TabularService:
    def __init__(self, stores_info: Dict[str, StoreInfo], default_db: Optional[str] = None):
        """
        Initialize the TabularService.

        :param stores_info: Mapping of database names to their StoreInfo.
        :param default_db: Optional name of the default database to fall back to
                           if the requested one is unknown.
        """
        self.stores_info = stores_info
        self.default_db = default_db or (next(iter(stores_info.keys())) if stores_info else None)

    def _get_store(self, db_name: str) -> Tuple[SQLTableStore, str]:
        """
        Retrieve the SQLTableStore for the given database name.
        Falls back to the default database if db_name is unknown.
        """
        if db_name not in self.stores_info:
            logger.warning(f"Unknown database '{db_name}', falling back to default database '{self.default_db}'")
            if not self.default_db or self.default_db not in self.stores_info:
                raise ValueError(f"Unknown database: {db_name} and no valid fallback configured")
            db_name = self.default_db
        return self.stores_info[db_name].store, db_name

    def _check_write_allowed(self, db_name: str):
        store = self.stores_info.get(db_name)
        if store and store.mode != "read_and_write":
            raise PermissionError(f"Write operations are not allowed on database '{db_name}'")

    def _sanitize_table_name(self, name: str) -> str:
        return name.replace("-", "_")

    def _format_date(self, dt: datetime) -> str:
        return dt.isoformat()

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

    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def delete_table(self, user: KeycloakUser, db_name: str, table_name: str) -> None:
        store, actual_db = self._get_store(db_name)
        self._check_write_allowed(actual_db)
        try:
            store.delete_table(table_name)
            logger.info(f"Table '{table_name}' deleted from database '{actual_db}'")
        except Exception as e:
            logger.error(f"Failed to delete table '{table_name}' from '{actual_db}': {e}")
            raise

    @authorize(action=Action.READ, resource=Resource.TABLES_DATABASES)
    def list_databases(self, user: KeycloakUser) -> List[str]:
        return list(self.stores_info.keys())

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def get_schema(self, user: KeycloakUser, db_name: str, table_name: str) -> TabularSchemaResponse:
        table_name = self._sanitize_table_name(table_name)
        store, db_name = self._get_store(db_name)
        schema = store.get_table_schema(table_name)
        columns = [TabularColumnSchema(name=col, dtype=self._map_sql_type_to_literal(dtype)) for col, dtype in schema]
        count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table_name}"')
        row_count = int(count_df["count"].iloc[0])
        return TabularSchemaResponse(db_name=db_name, table_name=table_name, columns=columns, row_count=row_count)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables(self, user: KeycloakUser, db_name: str) -> ListTableResponse:
        store, db_name = self._get_store(db_name)
        table_names = store.list_tables()
        return ListTableResponse(db_name=db_name, tables=table_names)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    def list_tables_with_schema(self, user: KeycloakUser, db_name: str) -> list[TabularSchemaResponse]:
        store, db_name = self._get_store(db_name)
        responses = []
        table_names = store.list_tables()
        for table in table_names:
            try:
                schema_info = store.get_table_schema(table)
                columns = [TabularColumnSchema(name=col_name, dtype=self._map_sql_type_to_literal(col_type)) for col_name, col_type in schema_info]
                count_df = store.execute_sql_query(f'SELECT COUNT(*) AS count FROM "{table}"')
                row_count = int(count_df["count"].iloc[0])
                responses.append(TabularSchemaResponse(db_name=db_name, table_name=table, columns=columns, row_count=row_count))
            except Exception as e:
                logger.warning(f"[{db_name}] Failed to load schema for {table}: {e}")
                continue
        return responses

    # Read-only queries (SELECT)
    @authorize(action=Action.READ, resource=Resource.TABLES)
    def query_read(self, user: KeycloakUser, db_name: str, request: RawSQLRequest) -> TabularQueryResponse:
        sql = request.query.strip()
        if not sql.lower().lstrip().startswith("select"):
            raise ValueError("Only SELECT statements are allowed on the read endpoint")
        store, db_name = self._get_store(db_name)
        df = store.execute_sql_query(sql)
        return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=df.to_dict(orient="records"), error=None)

    # Write queries (UPDATE, CREATE, DELETE)
    @authorize(action=Action.UPDATE, resource=Resource.TABLES)
    @authorize(action=Action.CREATE, resource=Resource.TABLES)
    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    def query_write(self, user: KeycloakUser, db_name: str, request: RawSQLRequest) -> TabularQueryResponse:
        sql = request.query.strip()
        if not sql:
            raise ValueError("Empty SQL string provided")
        self._check_write_allowed(db_name)
        store, db_name = self._get_store(db_name)
        store.execute_update_query(sql)
        return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=[], error=None)
