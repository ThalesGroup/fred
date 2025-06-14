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
In-memory implementation of the MetricStore interface.

This module provides a singleton-based in-memory metric store that can store,
aggregate, and retrieve numerical and categorical metrics over time. Intended
for use in development, testing, or non-persistent monitoring setups.
"""

import logging
from datetime import datetime
from typing import List, Dict, DefaultDict, Any
from collections import defaultdict
from statistics import mean
from pydantic import BaseModel

from fred.monitoring.metric_store import MetricStore, Metric, Precision, Aggregation
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric

logger = logging.getLogger("InMemoryMetricStore")
logger.setLevel(logging.INFO)


def flatten_numeric_fields(prefix: str, obj: Any) -> Dict[str, float]:
    """
    Recursively flattens an object (BaseModel or dict) to extract all numerical fields.

    Args:
        prefix (str): Prefix to prepend to field names for nested structures.
        obj (Any): Object to flatten, typically a Pydantic model or dictionary.

    Returns:
        Dict[str, float]: A flat dictionary mapping dotted field names to float values.
    """

    flat: Dict[str, float] = {}
    if isinstance(obj, BaseModel):
        data = obj.model_dump(exclude_none=True)
    elif isinstance(obj, dict):
        data = obj
    else:
        return flat

    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, (int, float)):
            flat[full_key] = float(v)
        elif isinstance(v, (dict, BaseModel)):
            flat.update(flatten_numeric_fields(full_key, v))

    return flat


class InMemoryMetricStore(MetricStore):
    """
    Singleton in-memory implementation of the MetricStore interface.

    Stores metrics in a list, supports filtering by date range,
    and provides aggregation over time buckets (second, minute, hour, day).
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        """
        Ensures that only one instance of the store is created (singleton pattern).
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._metrics: List[Metric] = []
            InMemoryMetricStore._initialized = True
            logger.info("Initialized InMemoryMetricStore")

    def add_metric(self, metric: Metric) -> None:
        """
        Adds a new metric to the store.

        Args:
            metric (Metric): The metric instance to store.
        """
        self._metrics.append(metric)
        logger.debug(f"Added metric: {metric}")

    def get_all(self) -> List[Metric]:
        """
        Returns all metrics currently stored.

        Returns:
            List[Metric]: List of all stored metrics.
        """
        return self._metrics   

    def get_by_date_range(self, start: datetime, end: datetime) -> List[Metric]:
        """
        Filters and returns metrics whose timestamp falls within the given date range.

        Args:
            start (datetime): Start of the date range.
            end (datetime): End of the date range.

        Returns:
            List[Metric]: Filtered list of metrics.
        """
        return [
            m for m in self._metrics
            if m.timestamp and start.timestamp() <= m.timestamp <= end.timestamp()
        ]

    def get_numerical_aggregated_by_precision(
        self, start: datetime, end: datetime, precision: Precision, agg: Aggregation
    ) -> List[NumericalMetric]:
        """
        Aggregates numerical metrics over time buckets using the specified precision and aggregation method.

        Args:
            start (datetime): Start of the date range.
            end (datetime): End of the date range.
            precision (str): Time granularity ('sec', 'min', 'hour', 'day').
            agg (str): Aggregation method ('avg', 'min', 'max', 'sum').

        Returns:
            List[NumericalMetric]: Aggregated metrics grouped by time buckets.
        """
        metrics = self.get_by_date_range(start, end)

        def round_bucket(ts: float) -> str:
            dt = datetime.fromtimestamp(ts)
            if precision == Precision.sec:
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            elif precision == Precision.min:
                return dt.strftime("%Y-%m-%d %H:%M")
            elif precision == Precision.hour:
                return dt.strftime("%Y-%m-%d %H:00")
            elif precision == Precision.day:
                return dt.strftime("%Y-%m-%d")
            return dt.isoformat()

        buckets: DefaultDict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

        for m in metrics:
            if m.timestamp is None:
                continue
            bucket = round_bucket(m.timestamp)

            # Recursively extract all float fields
            flat_fields = flatten_numeric_fields("", m)
            for key, value in flat_fields.items():
                buckets[bucket][key].append(value)

        result: List[NumericalMetric] = []
        for bucket_key, field_values in sorted(buckets.items()):
            values: Dict[str, float] = {}
            for field, val_list in field_values.items():
                if not val_list:
                    continue
                if agg == Aggregation.avg:
                    values[field] = round(mean(val_list), 4)
                elif agg == Aggregation.max:
                    values[field] = round(max(val_list), 4)
                elif agg == Aggregation.min:
                    values[field] = round(min(val_list), 4)
                elif agg == Aggregation.sum:
                    values[field] = round(sum(val_list), 4)
            result.append(NumericalMetric(bucket=bucket_key, values=values))

        return result

    def get_categorical_rows_by_date_range(
        self, start: datetime, end: datetime
    ) -> List[CategoricalMetric]:
        """
        Extracts categorical fields from metrics within the specified date range.

        Args:
            start (datetime): Start of the date range.
            end (datetime): End of the date range.

        Returns:
            List[CategoricalMetric]: List of categorical metric representations.
        """
        metrics = self.get_by_date_range(start, end)
        result: List[CategoricalMetric] = []
        for m in metrics:
            result.append(CategoricalMetric(
                timestamp=m.timestamp,
                user_id=m.user_id,
                session_id=m.session_id,
                model_name=m.model_name,
                model_type=m.model_type,
                finish_reason=m.finish_reason,
                id=getattr(m, "id", None),
                system_fingerprint=m.system_fingerprint,
                service_tier=m.service_tier
            ))
        return result



def get_metric_store() -> InMemoryMetricStore:
    """
    Returns the singleton instance of InMemoryMetricStore.

    Returns:
        InMemoryMetricStore: The singleton instance.
    """
    return InMemoryMetricStore()