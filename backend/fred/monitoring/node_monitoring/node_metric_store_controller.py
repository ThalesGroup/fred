from fastapi import APIRouter
import logging

from fred.monitoring.metric_controller_factory import register_metric_routes
from fred.monitoring.node_monitoring.node_metric_type import NodeMetric
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric
from fred.monitoring.node_monitoring.node_metric_store import get_node_metric_store

logger = logging.getLogger(__name__)


class NodeMetricStoreController:
    """
    FastAPI controller for metrics collected from LangGraph nodes (NodeMetricStore).

    Exposes:
    - /metrics/nodes → returns raw node metrics within a time window.
    """
    def __init__(self, router: APIRouter):
        store = get_node_metric_store()
        register_metric_routes(
            router=router,
            store=store,
            MetricType=NodeMetric,
            NumericalType=NumericalMetric,
            CategoricalType=CategoricalMetric,
            prefix="nodes"
        )
