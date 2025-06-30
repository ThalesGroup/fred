from typing import Optional
from fred.monitoring.base_hybrid_store import HybridJsonlStore
from fred.monitoring.node_monitoring.node_metric_type import NodeMetric
from fred.monitoring.metric_types import CategoricalMetric
from fred.common.structure import MetricsStorageConfig
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_instance: Optional["NodeMetricStore"] = None

class NodeMetricStore(HybridJsonlStore[NodeMetric]):
    def get_categorical_rows_by_date_range(self, start: datetime, end: datetime):
        metrics = self.get_by_date_range(start, end)
        return [
            CategoricalMetric(
                timestamp=m.timestamp,
                user_id=m.user_id,
                session_id=m.session_id,
                agent_name=m.agent_name,
                model_name=m.model_name,
                model_type=None,
                finish_reason=None,
                id=None,
                system_fingerprint=None,
                service_tier=None
            )
            for m in metrics
        ]

def create_node_metric_store(config: MetricsStorageConfig) -> NodeMetricStore:
    global _instance
    if _instance is None:
        _instance = NodeMetricStore(
            config=config,
            filename="tool_metrics.jsonl",
            model=NodeMetric
        )
    return _instance
def get_node_metric_store() -> NodeMetricStore:
    if _instance is None:
        raise RuntimeError("NodeMetricStore not initialized")
    return _instance
