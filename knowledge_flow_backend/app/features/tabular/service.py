# tabular_service.py

import pandas as pd
import io
import logging
from typing import List
from pandas.api.types import (
    is_string_dtype, is_numeric_dtype, is_bool_dtype, is_datetime64_any_dtype
)
import duckdb

from app.features.tabular.structures import TabularColumnSchema, TabularDatasetMetadata, TabularQueryRequest, TabularQueryResponse, TabularSchemaResponse
from app.features.tabular.utils import plan_to_sql
from app.features.tabular.structures import SQLQueryPlan
from app.application_context import ApplicationContext

logger = logging.getLogger(__name__)


class TabularService:
    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.tabular_store = self.context.get_tabular_store()

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
