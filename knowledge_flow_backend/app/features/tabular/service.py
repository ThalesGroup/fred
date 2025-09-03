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
from datetime import datetime
from typing import List, Dict
import pandas as pd

from fred_core.store.sql_store import SQLTableStore
from fred_core.store.structures import StoreInfo
from app.features.tabular.structures import TabularColumnSchema, RawSQLRequest, TabularQueryResponse, TabularSchemaResponse, DTypes


logger = logging.getLogger(__name__)


class TabularService:
    def __init__(self, stores_info: Dict[str, StoreInfo]):
        self.stores_info = stores_info

    def _get_store(self, db_name: str) -> SQLTableStore:
        if db_name not in self.stores_info:
            raise ValueError(f"Unknown database: {db_name}")
        return self.stores_info[db_name].store

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

    def delete_table(self, db_name: str, table_name: str) -> None:
        self._check_write_allowed(db_name)
        store = self._get_store(db_name)
        store.delete_table(table_name)

    def list_databases(self) -> List[str]:
        return list(self.stores_info.keys())

    def get_schema(self, db_name: str, document_name: str) -> TabularSchemaResponse:
        table_name = self._sanitize_table_name(document_name)
        store = self._get_store(db_name)

        schema = store.get_table_schema(table_name)
        columns = [TabularColumnSchema(name=col, dtype=self._map_sql_type_to_literal(dtype)) for col, dtype in schema]

        count_df = store.execute_sql_query(f"SELECT COUNT(*) AS count FROM {table_name}")
        row_count = count_df["count"][0]

        return TabularSchemaResponse(document_name=document_name, columns=columns, row_count=row_count)

    def list_tables_with_schema(self, db_name: str) -> list[TabularSchemaResponse]:
        store = self._get_store(db_name)
        responses = []
        table_names = store.list_tables()

        for table in table_names:
            try:
                schema_info = store.get_table_schema(table)
                columns = [TabularColumnSchema(name=col_name, dtype=self._map_sql_type_to_literal(col_type)) for col_name, col_type in schema_info]
                count_df = store.execute_sql_query(f"SELECT COUNT(*) AS count FROM {table}")
                row_count = count_df["count"][0]

                responses.append(TabularSchemaResponse(document_name=table, columns=columns, row_count=row_count))
            except Exception as e:
                logger.warning(f"[{db_name}] Failed to load schema for {table}: {e}")
                continue

        return responses

    def query(self, db_name: str, document_name: str, request: RawSQLRequest) -> TabularQueryResponse:
        store = self._get_store(db_name)
        sql = request.query.strip()

        if not sql:
            raise ValueError("Empty SQL string provided")

        try:
            is_write = not sql.lower().lstrip().startswith("select")
            if is_write:
                self._check_write_allowed(db_name)
                logger.info(f"[{db_name}] Executing SQL: {sql}")
                store.execute_update_query(sql)
                rows = []
            else:
                logger.info(f"[{db_name}] Executing SQL: {sql}")
                df = store.execute_sql_query(sql)
                rows = df.to_dict(orient="records")
            return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=rows, error=None)

        except Exception as e:
            logger.error(f"[{db_name}] Error during query execution: {e}", exc_info=True)
            return TabularQueryResponse(db_name=db_name, sql_query=sql, rows=[], error=str(e))
