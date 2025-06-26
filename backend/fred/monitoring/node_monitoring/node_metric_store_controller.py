from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Annotated, List, Tuple
import logging

from fred.monitoring.node_monitoring.hybrid_node_metric_store import (
    HybridNodeMetricStore,
    get_node_metric_store,
)
from fred.monitoring.node_monitoring.metric_types import NodeMetric, NumericalMetric, CategoricalMetric
from fred.monitoring.metric_store import Aggregation, Precision

logger = logging.getLogger(__name__)

def parse_dates(start: str, end: str) -> Tuple[datetime, datetime]:
    try:
        return datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates. Use ISO 8601 format.")

class NodeMetricStoreController:
    """
    FastAPI controller for metrics collected from LangGraph nodes (HybridNodeMetricStore).

    Exposes:
    - /metrics/nodes → returns raw node metrics within a time window.
    """
    def __init__(self, router: APIRouter):
        self.metric_store: HybridNodeMetricStore = get_node_metric_store()

        @router.get(
            "/metrics/nodes/all",
            response_model=List[NodeMetric],
            tags=["Node Metrics"],
            summary="List raw node metrics",
            description="Return every stored node metric whose timestamp is within the given date range.",
        )
        def get_node_metrics(
            start: Annotated[str, Query(description="Start date in ISO 8601 format")],
            end: Annotated[str, Query(description="End date in ISO 8601 format")]
        ) -> List[NodeMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_by_date_range(start_dt, end_dt)

        @router.get(
            "/metrics/nodes/numerical",
            response_model=List[NumericalMetric],
            tags=["Metrics"],
            summary="Aggregate numerical node metrics",
            description="Aggregate node metrics into time buckets (precision) and compute the selected aggregation (avg, min, max, sum).",
        )
        def get_node_numerical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()],
            precision: Precision = Precision.hour,
            agg: Aggregation = Aggregation.avg,
        ) -> List[NumericalMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_numerical_aggregated_by_precision(
                start=start_dt, end=end_dt, precision=precision, agg=agg
            )

        @router.get(
            "/metrics/nodes/categorical",
            response_model=List[CategoricalMetric],
            tags=["Metrics"],
            summary="List categorical node metrics",
            description="Return categorical node metric rows inside the date range (e.g., user, session, model info).",
        )
        def get_node_categorical_metrics(
            start: Annotated[str, Query()],
            end: Annotated[str, Query()]
        ) -> List[CategoricalMetric]:
            start_dt, end_dt = parse_dates(start, end)
            return self.metric_store.get_categorical_rows_by_date_range(
                start=start_dt, end=end_dt
            )
