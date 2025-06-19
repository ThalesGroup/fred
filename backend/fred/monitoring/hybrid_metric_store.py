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
from fred.monitoring.metric_store import MetricStore, Metric
from fred.monitoring.metric_types import NumericalMetric, CategoricalMetric
from fred.monitoring.inmemory_metric_store import flatten_numeric_fields

logger = logging.getLogger(__name__)

class HybridMetricStore(MetricStore):
    """
    Combines in-memory speed with file persistence (JSONL).
    """

    def __init__(self, config: MetricsStorageConfig):
        self._metrics: List[Metric] = []
        raw_path = config.settings.local_path
        self.data_path = os.path.expanduser(os.path.join(raw_path, "metrics.jsonl"))
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        self._lock = Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r") as f:
                for line in f:
                    self._metrics.append(Metric(**json.loads(line)))
            logger.info(f"HybridMetricStore: Loaded {len(self._metrics)} metrics.")

    def _save(self, metric: Metric):
        with open(self.data_path, "a") as f:
            f.write(metric.model_dump_json() + "\n")

    def add_metric(self, metric: Metric) -> None:
        with self._lock:
            self._metrics.append(metric)
            self._save(metric)
            logger.debug(f"HybridMetricStore: Metric added and persisted.")

    def get_all(self) -> List[Metric]:
        return self._metrics

    def get_by_date_range(self, start: datetime, end: datetime) -> List[Metric]:
        return [
            m for m in self._metrics
            if m.timestamp and start.timestamp() <= m.timestamp <= end.timestamp()
        ]

    def get_numerical_aggregated_by_precision(
        self, start: datetime, end: datetime, precision: str, agg: str
    ) -> List[NumericalMetric]:
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
            bucket = round_bucket(m.timestamp)
            flat_fields = flatten_numeric_fields("", m)
            for key, value in flat_fields.items():
                buckets[bucket][key].append(value)

        result: List[NumericalMetric] = []
        for bucket_key, field_values in sorted(buckets.items()):
            values: Dict[str, float] = {}
            for field, val_list in field_values.items():
                if not val_list:
                    continue
                if agg == "avg":
                    values[field] = round(mean(val_list), 4)
                elif agg == "max":
                    values[field] = round(max(val_list), 4)
                elif agg == "min":
                    values[field] = round(min(val_list), 4)
                elif agg == "sum":
                    values[field] = round(sum(val_list), 4)
            result.append(NumericalMetric(bucket=bucket_key, values=values))

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
                model_name=m.model_name,
                model_type=m.model_type,
                finish_reason=m.finish_reason,
                id=getattr(m, "id", None),
                system_fingerprint=m.system_fingerprint,
                service_tier=m.service_tier
            )
            for m in metrics
        ]

# Singleton accessor
_instance: Optional[HybridMetricStore] = None

def create_metric_store(config: MetricsStorageConfig) -> HybridMetricStore:
    global _instance
    if _instance is None:
        _instance = HybridMetricStore(config)
    return _instance

def get_metric_store() -> HybridMetricStore:
    """
    Returns the initialized HybridMetricStore singleton.

    Raises:
        RuntimeError: If the metric store has not been initialized yet.
    """
    if _instance is None:
        raise RuntimeError(
            "HybridMetricStore has not been initialized. "
            "Call `get_create_metric_store(config)` once during application startup."
        )
    return _instance
