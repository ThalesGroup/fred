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
# Refactored tabular_service.py (main modifications applied)

import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from app.features.tabular.structures import (
    TabularColumnSchema, TabularDatasetMetadata, TabularQueryRequest,
    TabularQueryResponse, TabularSchemaResponse, HowToMakeAQueryResponse,
    TabularAggregationResponse, AggregatedBucket, Precision, SQLQueryPlan
)
from app.features.tabular.utils import plan_to_sql
from app.application_context import ApplicationContext

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
    
    def list_datasets_with_schema(self) -> List[TabularSchemaResponse]:
        results = []
        for table in self.tabular_store.list_tables():
            schema_info = self.tabular_store.get_table_schema(table)
            columns = [
                TabularColumnSchema(name=col_name, dtype=self._map_duckdb_type_to_literal(col_type))
                for col_name, col_type in schema_info
            ]
            row_count_df = self.tabular_store.execute_sql_query(f"SELECT COUNT(*) AS count FROM {table}")
            row_count = row_count_df['count'][0]
            results.append(TabularSchemaResponse(
                document_name=table,
                columns=columns,
                row_count=row_count
            ))
        return results

    def query(self, document_name: str, request: TabularQueryRequest) -> TabularQueryResponse:
        sql = request.query if isinstance(request.query, str) else plan_to_sql(request.query)
        logger.info(f"Executing SQL: {sql}")
        df = self.tabular_store.execute_sql_query(sql)
        return TabularQueryResponse(document_name=document_name, rows=df.to_dict(orient="records"))

    def how_to_make_a_query(self) -> HowToMakeAQueryResponse:
        return HowToMakeAQueryResponse(how="""... (identique à la version précédente) ...""")

    def _get_bucket_expression(self, precision: str, timestamp_column: str) -> str:
        return {
            "sec": f"strftime('%Y-%m-%d %H:%M:%S', {timestamp_column})",
            "min": f"strftime('%Y-%m-%d %H:%M', {timestamp_column})",
            "hour": f"strftime('%Y-%m-%d %H:00', {timestamp_column})",
            "day": f"strftime('%Y-%m-%d', {timestamp_column})"
        }.get(precision, None) or (lambda: (_ for _ in ()).throw(ValueError(f"Unsupported precision: {precision}")))()

    def get_aggregated_metrics(self, table: str, start: datetime, end: datetime, precision: str,
                                agg_mapping: Dict[str, str], groupby_fields: Optional[List[str]] = None,
                                timestamp_column: str = "date") -> TabularAggregationResponse:
        table_name = self._sanitize_table_name(table)
        groupby_fields = groupby_fields or []

        bucket_expr = self._get_bucket_expression(precision, timestamp_column)
        select_fields = [f"{bucket_expr} AS time_bucket"] + groupby_fields
        for col, op in agg_mapping.items():
            select_fields.append(f"{op.upper()}({col}) AS '{col}--{op}'")

        sql = f"""
        SELECT {', '.join(select_fields)}
        FROM {table_name}
        WHERE {timestamp_column} BETWEEN '{self._format_date(start)}' AND '{self._format_date(end)}'
        GROUP BY {', '.join(['time_bucket'] + groupby_fields)}
        ORDER BY time_bucket
        """

        df = self.tabular_store.execute_sql_query(sql)
        buckets = []
        for _, row in df.iterrows():
            values = {k: v for k, v in row.items() if k not in ['time_bucket'] + groupby_fields}
            entry = {"time_bucket": row["time_bucket"], "values": values}
            if groupby_fields:
                entry["groupby_fields"] = {k: row[k] for k in groupby_fields}
            buckets.append(entry)

        return TabularAggregationResponse(buckets=buckets).model_dump(exclude_none=True)

    def get_global_aggregation(self, table: str, agg_mapping: Dict[str, str], groupby_fields: Optional[List[str]] = None,
                                timestamp_column: str = "date", start: Optional[datetime] = None,
                                end: Optional[datetime] = None) -> TabularAggregationResponse:
        table_name = self._sanitize_table_name(table)
        groupby_fields = groupby_fields or []

        select_parts = [f"{op.upper()}({col}) AS '{col}--{op}'" for col, op in agg_mapping.items()]
        if groupby_fields:
            select_parts = groupby_fields + select_parts
            group_clause = f"GROUP BY {', '.join(groupby_fields)}"
        else:
            group_clause = ""

        where_clause = ""
        if start and end:
            where_clause = f"WHERE {timestamp_column} BETWEEN '{self._format_date(start)}' AND '{self._format_date(end)}'"

        sql = f"SELECT {', '.join(select_parts)} FROM {table_name} {where_clause} {group_clause}"
        df = self.tabular_store.execute_sql_query(sql)

        buckets = []
        for _, row in df.iterrows():
            values = {k: v for k, v in row.items() if k not in groupby_fields}
            entry = {"time_bucket": "global", "values": values}
            if groupby_fields:
                entry["groupby_fields"] = {k: row[k] for k in groupby_fields}
            buckets.append(entry)

        return TabularAggregationResponse(buckets=buckets).model_dump(exclude_none=True)

    def get_aggregated_metrics_or_global(self, table: str, start: Optional[datetime], end: Optional[datetime],
                                         precision: Precision, agg_mapping: Dict[str, str],
                                         groupby_fields: Optional[List[str]] = None,
                                         timestamp_column: str = "date") -> TabularAggregationResponse:
        if precision == Precision.all:
            return self.get_global_aggregation(
                table=table,
                agg_mapping=agg_mapping,
                groupby_fields=groupby_fields,
                timestamp_column=timestamp_column,
                start=start,
                end=end
            )
        if not start or not end:
            raise ValueError("Start and end datetime must be provided for non-global aggregations")

        return self.get_aggregated_metrics(
            table=table,
            start=start,
            end=end,
            precision=precision,
            agg_mapping=agg_mapping,
            groupby_fields=groupby_fields,
            timestamp_column=timestamp_column
        )
