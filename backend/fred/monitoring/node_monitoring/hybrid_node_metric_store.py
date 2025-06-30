# fred/monitoring/hybrid_metric_store.py

import os
import json
import logging
from datetime import datetime
from threading import Lock
from typing import List, Optional, DefaultDict, Dict
from statistics import mean
from collections import defaultdict

from fred.common.structure import MetricsStorageConfig
from fred.monitoring.metric_store import MetricStore
from fred.monitoring.node_monitoring.metric_types import NodeMetric,NumericalMetric,CategoricalMetric
from fred.monitoring.metric_util import flatten_numeric_fields

logger = logging.getLogger(__name__)

class HybridNodeMetricStore(MetricStore):
    """
    Combines in-memory speed with file persistence (JSONL).
    """

    def __init__(self, config: MetricsStorageConfig):
        self._metrics: List[NodeMetric] = []
        raw_path = config.settings.local_path
        self.data_path = os.path.expanduser(os.path.join(raw_path, "metrics.jsonl"))
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        self._lock = Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r") as f:
                for line in f:
                    logger.info(line)
                    self._metrics.append(NodeMetric(**json.loads(line)))
            logger.info(f"HybridNodeMetricStore: Loaded {len(self._metrics)} metrics.")

    def _save(self, metric: NodeMetric):
        with open(self.data_path, "a") as f:
            f.write(metric.model_dump_json() + "\n")

    def add_metric(self, metric: NodeMetric) -> None:
        with self._lock:
            self._metrics.append(metric)
            self._save(metric)
            logger.debug(f"HybridNodeMetricStore: NodeMetric added and persisted.")

    def get_all(self) -> List[NodeMetric]:
        return self._metrics

    def get_by_date_range(self, start: datetime, end: datetime) -> List[NodeMetric]:
        return [
            m for m in self._metrics
            if m.timestamp and start.timestamp() <= m.timestamp <= end.timestamp()
        ]
    
    def get_aggregate_numerical_metrics_by_time_and_group(
        self,
        start: datetime,
        end: datetime,
        precision: str,
        agg_mapping: Dict[str, str],
        groupby_fields: Optional[List[str]] = None
    ) -> List[NumericalMetric]:
        
        if groupby_fields is None:
            groupby_fields = []

        metrics = self.get_by_date_range(start, end)

        def round_bucket(ts: float) -> str:
            dt = datetime.fromtimestamp(ts)
            if precision == "sec":
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            elif precision == "min":
                return dt.strftime("%Y-%m-%d %H:%M")
            elif precision == "hour":
                return dt.strftime("%Y-%m-%d %H:00")
            elif precision == "day":
                return dt.strftime("%Y-%m-%d")
            return dt.isoformat()

        buckets: DefaultDict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

        for m in metrics:
            if m.timestamp is None:
                continue

            time_bucket = round_bucket(m.timestamp)

            # Extraire les valeurs de groupby
            grouping_values = []
            for field in groupby_fields:
                value = getattr(m, field, None)
                grouping_values.append(str(value) if value is not None else "null")

            # Clé du bucket = time_bucket + grouping fields
            bucket_key = (time_bucket, *grouping_values)

            flat_fields = flatten_numeric_fields("", m)
            for key, value in flat_fields.items():
                buckets[bucket_key][key].append(value)

        result: List[NumericalMetric] = []
        for bucket_key, field_values in sorted(buckets.items()):
            time_bucket = bucket_key[0]
            group_values = bucket_key[1:]
            bucket_str = "|".join([time_bucket] + list(group_values))

            values: Dict[str, float] = {}
            for field, val_list in field_values.items():
                if not val_list:
                    continue
                op = agg_mapping.get(field)
                if op is None:
                    continue
                if op == "avg":
                    values[field] = round(mean(val_list), 4)
                elif op == "max":
                    values[field] = round(max(val_list), 4)
                elif op == "min":
                    values[field] = round(min(val_list), 4)
                elif op == "sum":
                    values[field] = round(sum(val_list), 4)

            result.append(NumericalMetric(bucket=bucket_str, values=values))

        return result

    
    def get_categorical_rows_by_date_range(
        self, start: datetime, end: datetime
    ) -> List[CategoricalMetric]:
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


# Singleton accessor
_instance: Optional[HybridNodeMetricStore] = None

def create_node_metric_store(config: MetricsStorageConfig) -> HybridNodeMetricStore:
    global _instance
    if _instance is None:
        _instance = HybridNodeMetricStore(config)
    return _instance

def get_node_metric_store() -> HybridNodeMetricStore:
    """
    Returns the initialized HybridNodeMetricStore singleton.

    Raises:
        RuntimeError: If the metric store has not been initialized yet.
    """
    if _instance is None:
        raise RuntimeError(
            "HybridNodeMetricStore has not been initialized. "
            "Call `get_create_metric_store(config)` once during application startup."
        )
    return _instance
