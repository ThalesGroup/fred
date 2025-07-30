# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
metric_controller_factory.py

Factory for registering generic metric routes on a FastAPI router.

Supports:
- Raw retrieval within time windows.
- Numerical aggregation with flexible groupby and aggregation.
- Categorical extraction.

Designed to be reusable for both node and tool metrics by parameterizing store and models.
"""

from app.core.monitoring.metric_store import Precision
from fastapi import APIRouter, Query, HTTPException
from typing import List, Annotated
from datetime import datetime


def register_metric_routes(
    router: APIRouter, store, MetricType, NumericalType, CategoricalType, prefix: str
):
    """
    Registers standardized metric API endpoints on the given FastAPI router.

    Endpoints:
        /metrics/{prefix}/all : Raw metrics within a time window.
        /metrics/{prefix}/numerical : Aggregated numerical metrics with groupby support.
        /metrics/{prefix}/categorical : Extracted categorical dimensions.

    Args:
        router (APIRouter): The FastAPI router.
        store: The concrete metric store instance.
        MetricType: Pydantic model for raw metrics.
        NumericalType: Pydantic model for numerical aggregates.
        CategoricalType: Pydantic model for categorical rows.
        prefix (str): URL prefix (e.g., 'nodes' or 'tools').
    """

    def parse_dates(start: str, end: str) -> (datetime, datetime):
        return datetime.fromisoformat(start), datetime.fromisoformat(end)

    @router.get(f"/metrics/{prefix}/all", response_model=List[MetricType])
    def get_metrics(start: Annotated[str, Query()], end: Annotated[str, Query()]):
        start_dt, end_dt = parse_dates(start, end)
        return store.get_by_date_range(start_dt, end_dt)

    @router.get(f"/metrics/{prefix}/numerical", response_model=List[NumericalType])
    def get_node_numerical_metrics(
        start: Annotated[str, Query()],
        end: Annotated[str, Query()],
        precision: Precision = Precision.hour,
        agg: List[str] = Query(default=[]),
        groupby: List[str] = Query(default=[]),
    ):
        start_dt, end_dt = parse_dates(start, end)
        agg_mapping = {}
        for item in agg:
            try:
                field, op = item.split(":")
                agg_mapping[field] = op
            except ValueError:
                raise HTTPException(400, detail=f"Invalid agg parameter format: {item}")

        return store.get_aggregate_numerical_metrics_by_time_and_group(
            start=start_dt,
            end=end_dt,
            precision=precision,
            agg_mapping=agg_mapping,
            groupby_fields=groupby,
        )

    @router.get(f"/metrics/{prefix}/categorical", response_model=List[CategoricalType])
    def get_categorical(start: Annotated[str, Query()], end: Annotated[str, Query()]):
        start_dt, end_dt = parse_dates(start, end)
        return store.get_categorical_rows_by_date_range(start_dt, end_dt)
