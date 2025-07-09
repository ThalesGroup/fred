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
node_metric_store.py

Defines NodeMetricStore, a persistent store for NodeMetric entries
using a hybrid in-memory + JSONL file backend.

Features:
- Loads existing metrics from JSONL on startup.
- Thread-safe appending and saving.
- Filtering by time range.
- Conversion to categorical metrics for inspection.
"""

from typing import Optional
from app.monitoring.base_hybrid_store import HybridJsonlStore
from app.monitoring.node_monitoring.node_metric_type import NodeMetric
from app.monitoring.metric_types import CategoricalMetric
from app.common.structure import MetricsStorageConfig
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_instance: Optional["NodeMetricStore"] = None

class NodeMetricStore(HybridJsonlStore[NodeMetric]):
    """
    Concrete store for NodeMetric objects.

    Inherits:
        HybridJsonlStore[NodeMetric]: Provides base persistence and retrieval.

    Additional methods:
        - get_categorical_rows_by_date_range: Converts stored metrics to CategoricalMetric representations
          for analytics and filtering on categorical dimensions.
    """
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
    """
    Initializes and returns the singleton NodeMetricStore.

    Should be called once during app startup.

    Args:
        config (MetricsStorageConfig): Store configuration.

    Returns:
        NodeMetricStore: The initialized store instance.
    """
    global _instance
    if _instance is None:
        _instance = NodeMetricStore(
            config=config,
            filename="node_metrics.jsonl",
            model=NodeMetric
        )
    return _instance

def get_node_metric_store() -> NodeMetricStore:
    """
    Returns the singleton NodeMetricStore.

    Raises:
        RuntimeError: If the store has not been initialized.
    """
    if _instance is None:
        raise RuntimeError("NodeMetricStore not initialized")
    return _instance
