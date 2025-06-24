from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Annotated, List, Tuple
import logging

from fred.monitoring.tool_monitoring.hybrid_tool_metric_store import (
    HybridToolMetricStore,
    get_tool_metric_store
)
from fred.monitoring.tool_monitoring.metric_types import ToolMetric,NumericalMetric,CategoricalMetric
from fred.monitoring.metric_store import Aggregation, Precision

logger = logging.getLogger(__name__)


def parse_dates(start: str, end: str) -> Tuple[datetime, datetime]:
    try:
        return datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")


class ToolMetricStoreController:
    """
    FastAPI controller for metrics collected from tools (HybridToolMetricStore).

    Exposes:
    - /metrics/tools → returns raw tool metrics within a time window.
    """
    def __init__(self, router: APIRouter):
        self.metric_store: HybridToolMetricStore = get_tool_metric_store()

        @router.get(
            "/metrics/tools/all",
            response_model=List[ToolMetric],
            tags=["Tool Metrics"],
            summary="List raw tool metrics",
            description="Return every stored tool metric whose timestamp is within the given date range.",
        )
        def get_tool_metrics(
            start: Annotated[str, Query(description="Start date in ISO 8601 format")],
            end: Annotated[str, Query(description="End date in ISO 8601 format")]
        ) -> List[ToolMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_by_date_range(start_dt, end_dt)
        @router.get(
            "/metrics/tools/numerical",
            response_model=List[NumericalMetric],
            tags=["Metrics"],
            summary="Aggregate numerical metrics",
            description=(
                "Aggregate numerical metrics into time buckets of the chosen "
                "precision and apply the selected aggregation function."
            ),
        )
        def get_numerical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()],
            precision: Precision = Precision.hour,
            agg: Aggregation = Aggregation.avg,
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
            "/metrics/tools/categorical",
            response_model=List[CategoricalMetric],
            tags=["Metrics"],
            summary="List categorical metrics",
            description="Return categorical-only metric rows inside the date range.",
        )
        def get_categorical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()]
        ) -> List[CategoricalMetric]:
            """Retrieve categorical metrics (id, model, finish_reason, …) between the given dates."""
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_categorical_rows_by_date_range(
                start=start_dt, end=end_dt
            )
