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
import re
from datetime import datetime
from typing import List, Dict, Optional, Any

from app.application_context import ApplicationContext
from app.features.tabular.structures import (
    TabularColumnSchema,
    TabularDatasetMetadata,
    RawSQLRequest,
    TabularQueryResponse,
    TabularSchemaResponse,
)

logger = logging.getLogger(__name__)

class TabularService:
    def __init__(self):
        self.tabular_store = ApplicationContext.get_instance().get_tabular_store()

    def _sanitize_table_name(self, name: str) -> str:
        return name.replace('-', '_')

    def _format_date(self, dt: datetime) -> str:
        return dt.isoformat()

    def _map_duckdb_type_to_literal(self, duckdb_type: str) -> str:
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

    def list_tabular_datasets(self) -> List[TabularDatasetMetadata]:
        datasets = []
        for table_name in self.tabular_store.list_tables():
            try:
                count_df = self.tabular_store.execute_sql_query(
                    f"SELECT COUNT(*) AS count FROM {table_name}"
                )
                row_count = count_df["count"][0]
            except Exception as e:
                logger.warning(f"Failed to count rows for {table_name}: {e}")
                row_count = 0

            datasets.append(
                TabularDatasetMetadata(
                    document_name=table_name,
                    title=table_name,
                    description="",
                    tags=[],
                    domain="",
                    row_count=row_count,
                )
            )
        return datasets

    def get_schema(self, document_name: str) -> TabularSchemaResponse:
        table_name = document_name.replace("-", "_")
        schema = self.tabular_store.get_table_schema(table_name)

        columns = [
            TabularColumnSchema(name=col, dtype=self._map_duckdb_type_to_literal(dtype))
            for col, dtype in schema
        ]

        count_df = self.tabular_store.execute_sql_query(
            f"SELECT COUNT(*) AS count FROM {table_name}"
        )
        row_count = count_df["count"][0]

        return TabularSchemaResponse(
            document_name=document_name, columns=columns, row_count=row_count
        )
    
    def list_datasets_with_schema(self) -> list[TabularSchemaResponse]:
        responses = []
        table_names = self.tabular_store.list_tables()

        for table in table_names:
            try:
                schema_info = self.tabular_store.get_table_schema(table)
                columns = [
                    TabularColumnSchema(name=col_name, dtype=self._map_duckdb_type_to_literal(col_type))
                    for col_name, col_type in schema_info
                ]
                count_df = self.tabular_store.execute_sql_query(f"SELECT COUNT(*) AS count FROM {table}")
                row_count = count_df["count"][0]

                responses.append(
                    TabularSchemaResponse(
                        document_name=table,
                        columns=columns,
                        row_count=row_count
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to load schema for {table}: {e}")
                continue

        return responses

    def query(self, document_name: str, request: RawSQLRequest) -> TabularQueryResponse:
        if not isinstance(request.query, str):
            raise ValueError("Expected raw SQL string in request.query")

        sql = request.query.strip()

        # Vérifie s'il y a déjà un LIMIT dans la requête
        has_limit = re.search(r"\bLIMIT\b\s+\d+", sql, re.IGNORECASE) is not None

        # Si aucun LIMIT, ajoute "LIMIT 20"
        if not has_limit:
            sql = sql.rstrip(";") + " LIMIT 20"

        logger.info(f"🧠 Final SQL executed: {sql}")

        try:
            df = self.tabular_store.execute_sql_query(sql)
            rows = df.to_dict(orient="records")
            return TabularQueryResponse(document_name=document_name, rows=rows, error=None)
        except Exception as e:
            logger.error(f"Error during query execution: {e}", exc_info=True)
            return TabularQueryResponse(document_name=document_name, rows=[], error=str(e))
