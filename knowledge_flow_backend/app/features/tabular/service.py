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

# tabular_service.py

import logging
from typing import List

from app.features.tabular.structures import TabularColumnSchema, TabularDatasetMetadata, TabularQueryRequest, TabularQueryResponse, TabularSchemaResponse, HowToMakeAQueryResponse
from app.features.tabular.utils import plan_to_sql
from app.features.tabular.structures import SQLQueryPlan
from app.application_context import ApplicationContext

logger = logging.getLogger(__name__)


class TabularService:
    def __init__(self):
        self.tabular_store = ApplicationContext.get_instance().get_tabular_store()

    def _map_duckdb_type_to_literal(self, duckdb_type: str) -> str:
        """
        Map DuckDB SQL types to TabularColumnSchema dtype Literal.
        """
        duckdb_type = duckdb_type.lower()

        if any(x in duckdb_type for x in ["varchar", "string", "text"]):
            return "string"
        if "boolean" in duckdb_type:
            return "boolean"
        if "timestamp" in duckdb_type or "date" in duckdb_type or "time" in duckdb_type:
            return "datetime"
        if "double" in duckdb_type or "real" in duckdb_type or "float" in duckdb_type:
            return "float"
        if "int" in duckdb_type:
            return "integer"

        return "unknown"

    def get_schema(self, document_name: str) -> TabularSchemaResponse:
        table_name = document_name.replace('-', '_')
        schema_info = self.tabular_store.get_table_schema(table_name)

        columns = [
            TabularColumnSchema(name=col_name, dtype=self._map_duckdb_type_to_literal(col_type))
            for col_name, col_type in schema_info
        ]

        # Count rows
        count_sql = f"SELECT COUNT(*) AS count FROM {table_name}"
        count_df = self.tabular_store.execute_sql_query(count_sql)
        row_count = count_df['count'][0]

        return TabularSchemaResponse(
            document_name=document_name,
            columns=columns,
            row_count=row_count
        )

    def query(self, document_name: str, request: TabularQueryRequest) -> TabularQueryResponse:
        
        if isinstance(request.query, str):
            sql = request.query
        elif isinstance(request.query, SQLQueryPlan):
            sql = plan_to_sql(request.query)

        logger.info(f"Executing SQL: {sql}")
        df = self.tabular_store.execute_sql_query(sql)
        rows = df.to_dict(orient="records")

        return TabularQueryResponse(
            document_name=document_name,
            rows=rows
        )

    def list_tabular_datasets(self) -> List[TabularDatasetMetadata]:
        datasets = []

        tables = self.tabular_store.list_tables()
        for table_name in tables:
            # Count rows
            count_sql = f"SELECT COUNT(*) AS count FROM {table_name}"
            count_df = self.tabular_store.execute_sql_query(count_sql)
            count = count_df['count'][0]

            # Reverse UID convention
            document_name = table_name

            datasets.append(TabularDatasetMetadata(
                document_name=document_name,
                title=document_name,
                description="",
                tags=[],
                domain="",
                row_count=count
            ))

        return datasets
    
    def how_to_make_a_query(self) -> HowToMakeAQueryResponse:
        response = """
                Respond with a **JSON object** describing the SQL query plan. This will be transformed into SQL by the server.

                ## Fields:
                - `table` *(REQUIRED)*: main table to query.
                - `columns` *(OPTIONAL)*: columns to SELECT. Use `*` or leave empty to select all.
                - `filters` *(OPTIONAL)*: list of conditions for the WHERE clause.
                - `group_by`, `order_by`, `limit` *(OPTIONAL)*: standard SQL clauses.
                - `joins` *(OPTIONAL)*: list of joins with other tables.

                ### Filters:
                - `column`: the column to filter on.
                - `op`: SQL operator (e.g. '=', '<>', '>', '<', 'LIKE', 'IN').
                - `value` (can be scalar or list for IN).
                exemple: "filters": [{"column": "status", "op": "=", "value": "active"}]"

                ### OrderBySpec:
                - `column`: column.
                - `direction`: ASC or DESC, defaults to ASC.
                exemple: "order_by": [{"column": "user_id", "direction": "DESC"}]

                ### JoinSpec:
                - `table`: name of the table to join.
                - `on`: join condition.
                - `type`: join type (INNER, LEFT, etc.).

                ### AggregationSpec:
                - `function`: aggregation function (e.g. SUM, COUNT, AVG, etc.).
                - `column`: column to aggregate.
                - `alias`: result alias for the aggregated value.
                - `distinct` *(OPTIONAL)*: boolean. If true, applies DISTINCT to the aggregation (e.g. `COUNT(DISTINCT column)`).
                - `filter` *(OPTIONAL)*: dictionary of conditions applied *within* the aggregation using SQL FILTER (WHERE ...) syntax. Example: `{"status": "active"}` will generate `FILTER (WHERE status = 'active')`.

                - `aggregations` *(OPTIONAL)*: list of aggregation specifications to compute in SELECT.

                Always specify `table`. Use `joins`, `filters`, `aggregations`, `group_by`, `order_by`, `limit` as needed.
                """
        return HowToMakeAQueryResponse(how=response)

