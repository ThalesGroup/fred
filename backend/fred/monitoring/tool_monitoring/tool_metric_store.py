from typing import Optional
from fred.monitoring.base_hybrid_store import HybridJsonlStore
from fred.monitoring.tool_monitoring.tool_metric_type import ToolMetric
from fred.monitoring.metric_types import CategoricalMetric
from fred.common.structure import MetricsStorageConfig
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_instance: Optional["ToolMetricStore"] = None

class ToolMetricStore(HybridJsonlStore[ToolMetric]):
    def get_categorical_rows_by_date_range(self, start: datetime, end: datetime):
        metrics = self.get_by_date_range(start, end)
        return [
            CategoricalMetric(
                timestamp=m.timestamp,
                user_id=m.user_id,
                session_id=m.session_id,
                tool_name=m.tool_name
            )
            for m in metrics
        ]

def create_tool_metric_store(config: MetricsStorageConfig) -> ToolMetricStore:
    global _instance
    if _instance is None:
        _instance = ToolMetricStore(
            config=config,
            filename="tool_metrics.jsonl",
            model=ToolMetric
        )
    return _instance

def get_tool_metric_store() -> ToolMetricStore:
    if _instance is None:
        raise RuntimeError("ToolMetricStore not initialized")
    return _instance
