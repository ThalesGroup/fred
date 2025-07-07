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
tool_metric_store.py

Defines ToolMetricStore, a hybrid in-memory and JSONL-persistent store
for ToolMetric records.

Features:
- Thread-safe appending and reading.
- Time-window filtering.
- Conversion to categorical rows for analytics.
- Singleton pattern for global access.
"""

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
    """
    Persistent store for ToolMetric objects.

    Inherits:
        HybridJsonlStore[ToolMetric]: Base class handling JSONL persistence and in-memory cache.

    Additional methods:
        - get_categorical_rows_by_date_range: Converts ToolMetric to CategoricalMetric
          for categorical analyses.
    """
    def get_categorical_rows_by_date_range(self, start: datetime, end: datetime):
        """
        Returns ToolMetric records in the date range as CategoricalMetric entries.

        Extracts only categorical dimensions like user, session, tool name.

        Args:
            start (datetime): Start timestamp (inclusive).
            end (datetime): End timestamp (inclusive).

        Returns:
            List[CategoricalMetric]: Reduced categorical view of tool metrics.
        """
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
    """
    Initializes the singleton ToolMetricStore.

    Args:
        config (MetricsStorageConfig): Store configuration.

    Returns:
        ToolMetricStore: The initialized store instance.
    """
    global _instance
    if _instance is None:
        _instance = ToolMetricStore(
            config=config,
            filename="tool_metrics.jsonl",
            model=ToolMetric
        )
    return _instance

def get_tool_metric_store() -> ToolMetricStore:
    """
    Retrieves the singleton ToolMetricStore.

    Raises:
        RuntimeError: If the store has not been initialized.

    Returns:
        ToolMetricStore: The global store instance.
    """
    if _instance is None:
        raise RuntimeError("ToolMetricStore not initialized")
    return _instance
