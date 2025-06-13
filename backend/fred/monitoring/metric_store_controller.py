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


"""
FastAPI routes and controller for accessing metrics stored in an in-memory
MetricStore.

The module exposes three endpoints:

* **/metrics/all** – Returns raw MetaData objects in a date range.
* **/metrics/numerical** – Returns aggregated numerical metrics with configurable
  time precision and aggregation function.
* **/metrics/categorical** – Returns categorical-only metrics rows (id, model,
  finish_reason, …) for the given date range.

All query parameters use ISO 8601 date-time strings (e.g. ``2025-06-12T09:15:00``).
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import List, Tuple
import logging

from fred.monitoring.metric_store import MetricStore
from fred.monitoring.hybrid_metric_store import get_metric_store,HybridMetricStore
from fred.monitoring.metric_types import CategoricalMetric, MetaData, NumericalMetric

logger = logging.getLogger(__name__)


def parse_dates(start: str, end: str) -> Tuple[datetime, datetime]:
    """
    Convert **start** and **end** strings to :class:`datetime` objects.

    Args:
        start: Start date in ISO 8601 format (``YYYY-MM-DDThh:mm:ss``).
        end:   End date in ISO 8601 format.

    Returns:
        A tuple ``(start_dt, end_dt)`` with parsed datetimes.

    Raises:
        HTTPException: *400 Bad Request* if either string cannot be parsed.
    """
    try:
        return datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")


class MetricStoreController:
    """
    Wires the FastAPI router to the singleton :class:`~fred.monitoring.inmemory_metric_store.InMemoryMetricStore`.

    Instantiating this class adds three **GET** endpoints to the supplied router.

    Example
    -------
    ```python
    router = APIRouter()
    MetricStoreController(router)
    app.include_router(router)
    ```
    """
    def __init__(self, router: APIRouter):
        """
        Register metric routes on **router**.

        Args:
            router: FastAPI APIRouter where endpoints will be mounted.
        """
        self.metric_store: HybridMetricStore = get_metric_store()

        @router.get(
            "/metrics/all",
            response_model=List[MetaData],
            tags=["Metrics"],
            summary="List raw metrics",
            description="Return every stored metric whose timestamp is within the "
                        "given date range (no aggregation).",
        )
        def get_all_metrics(
            start: str = Query(..., description="Start date (ISO 8601)"),
            end: str = Query(..., description="End date (ISO 8601)"),
        ) -> List[MetaData]:
            """
            Retrieve all raw metrics between **start** and **end** (inclusive)."""
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_by_date_range(start_dt, end_dt)

        @router.get(
            "/metrics/numerical",
            response_model=List[NumericalMetric],
            tags=["Metrics"],
            summary="Aggregate numerical metrics",
            description=(
                "Aggregate numerical metrics into time buckets of the chosen "
                "precision and apply the selected aggregation function."
            ),
        )
        def get_numerical_metrics(
            start: str = Query(..., description="Start date (ISO 8601)"),
            end: str = Query(..., description="End date (ISO 8601)"),
            precision: str = Query(
                "hour",
                enum=["sec", "min", "hour", "day"],
                description="Time bucket size"
            ),
            agg: str = Query(
                "avg",
                enum=["avg", "max", "min", "sum"],
                description="Aggregation function"
            ),
        ) -> List[NumericalMetric]:
            """
            Aggregate numerical metrics over the specified date range.

            The store groups values into buckets of size **precision**
            (second/minute/hour/day) and computes the aggregate **agg**
            (average, min, max, sum) for each field.
            """
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_numerical_aggregated_by_precision(
                start=start_dt, end=end_dt, precision=precision, agg=agg
            )

        @router.get(
            "/metrics/categorical",
            response_model=List[CategoricalMetric],
            tags=["Metrics"],
            summary="List categorical metrics",
            description="Return categorical-only metric rows inside the date range.",
        )
        def get_categorical_metrics(
            start: str = Query(..., description="Start date (ISO 8601)"),
            end: str = Query(..., description="End date (ISO 8601)"),
        ) -> List[CategoricalMetric]:
            """Retrieve categorical metrics (id, model, finish_reason, …) between the given dates."""
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_categorical_rows_by_date_range(
                start=start_dt, end=end_dt
            )
