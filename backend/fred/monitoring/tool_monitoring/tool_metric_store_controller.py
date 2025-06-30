from fastapi import APIRouter
import logging

from fred.monitoring.metric_controller_factory import register_metric_routes
from fred.monitoring.tool_monitoring.tool_metric_type import ToolMetric
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric
from fred.monitoring.tool_monitoring.tool_metric_store import get_tool_metric_store

logger = logging.getLogger(__name__)


class ToolMetricStoreController:
    """
    FastAPI controller for metrics collected from LangGraph nodes (ToolMetricStore).

    Exposes:
    - /metrics/nodes → returns raw node metrics within a time window.
    """
    def __init__(self, router: APIRouter):
        store = get_tool_metric_store()
        register_metric_routes(
            router=router,
            store=store,
            MetricType=ToolMetric,
            NumericalType=NumericalMetric,
            CategoricalType=CategoricalMetric,
            prefix="tools"
        )