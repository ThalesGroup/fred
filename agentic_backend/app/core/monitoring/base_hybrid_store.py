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
base_hybrid_store.py

Provides HybridJsonlStore: a generic, thread-safe, hybrid (in-memory + JSONL) 
persistent store for metrics.

Features:
- Persists metrics in JSONL files.
- Loads existing records on startup.
- Supports time-range filtering.
- Flexible dynamic aggregation with custom groupby and aggregation functions.

Intended use:
- Backing stores for NodeMetricStore, ToolMetricStore, etc.
"""


import os
import json
import logging
from datetime import datetime
from threading import Lock
from typing import Type, TypeVar, Generic, List, Optional, Dict, DefaultDict, Any, Tuple
from statistics import mean
from collections import defaultdict

from app.common.structures import MetricsStorageConfig
from app.core.monitoring.metric_store import MetricStore, Precision
from app.core.monitoring.metric_util import flatten_numeric_fields
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class HybridJsonlStore(Generic[T], MetricStore):
    """
    Generic hybrid store for metrics.

    Stores any Pydantic model to a JSONL file and keeps an in-memory cache
    for fast reads and aggregations.

    Features:
    - Thread-safe writes.
    - Flexible time-bucket rounding.
    - Dynamic groupby and aggregation of numerical metrics.
    """

    def __init__(self, config: MetricsStorageConfig, filename: str, model: Type[T]):
        """
        Hybrid JSONL Store constructor.

        Args:
            config (MetricsStorageConfig): Holds settings, including local_path.
            filename (str): Name of the JSONL file for persistence.
            model (Type[T]): Pydantic model class to load/save.
        """
        self._metrics: List[T] = []
        self.model_cls = model

        raw_path = config.local_path
        self.data_path = os.path.expanduser(os.path.join(raw_path, filename))
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

        self._lock = Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r") as f:
                for line in f:
                    try:
                        self._metrics.append(self.model_cls(**json.loads(line)))
                    except Exception as e:
                        msg =(
                            f"\n\n❌ Failed to load metric from JSONL file: {self.data_path}\n"
                            f"   → invalid metric that does not match the expected schema for {self.model_cls.__name__}.\n"
                            f"   → Offending line: {line.strip()}\n"
                            f"   → Error: {type(e).__name__}: {e}\n\n"
                            f"💡 To fix this, you can either:\n"
                            f"   - Manually delete or fix the line in {self.data_path}\n"
                            f"   - Or delete the file entirely if the data isn't critical.\n"
                        )
                        raise RuntimeError(msg) from e
            logger.info(f"HybridJsonlStore: Loaded {len(self._metrics)} metrics from {self.data_path}")

    def _save(self, metric: T):
        with open(self.data_path, "a") as f:
            f.write(metric.model_dump_json() + "\n")

    def add_metric(self, metric: T) -> None:
        with self._lock:
            self._metrics.append(metric)
            self._save(metric)
            logger.debug("HybridJsonlStore: Metric added and persisted.")

    def get_all(self) -> List[T]:
        return self._metrics

    def get_by_date_range(self, start: datetime, end: datetime) -> List[T]:
        return [
            m for m in self._metrics
            if hasattr(m, 'timestamp') and m.timestamp and start.timestamp() <= m.timestamp <= end.timestamp()
        ]

    def _round_bucket(self, ts: float, precision: Precision) -> str:
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

    def get_aggregate_numerical_metrics_by_time_and_group(
        self,
        start: datetime,
        end: datetime,
        precision: str,
        agg_mapping: Dict[str, str],
        groupby_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Aggregates numerical fields from stored metrics over time buckets and groupby dimensions.

        Args:
            start (datetime): Start of the time window.
            end (datetime): End of the time window.
            precision (str): Time bucket granularity ('sec', 'min', 'hour', 'day').
            agg_mapping (Dict[str, str]): Mapping of field names to aggregation ops (avg, min, max, sum).
            groupby_fields (Optional[List[str]]): Fields to group by in addition to time buckets.

        Returns:
            List[Dict[str, Any]]: Each record includes time_bucket, groupby fields, and aggregated values.
        """
        if groupby_fields is None:
            groupby_fields = []

        # Filtrer les metrics par date
        metrics = self.get_by_date_range(start, end)

        # (time_bucket, *groupby) => { field -> [values] }
        buckets: DefaultDict[Tuple[str, ...], Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

        for m in metrics:
            if m.timestamp is None:
                continue

            # Round timestamp into bucket
            time_bucket = self._round_bucket(m.timestamp, Precision(precision))

            # Build groupby key parts
            grouping_values = []
            for field in groupby_fields:
                # Always add a value to maintain alignment with groupby_fields
                value = getattr(m, field, None)
                grouping_values.append(str(value) if value is not None else "_MISSING_")

            bucket_key = (time_bucket, *grouping_values)

            # Flatten all numeric fields in the metric
            flat_fields = flatten_numeric_fields("", m)
            for key, value in flat_fields.items():
                buckets[bucket_key][key].append(value)

        # Build the response
        result: List[Dict[str, Any]] = []

        for bucket_key, field_values in sorted(buckets.items()):
            time_bucket = bucket_key[0]
            group_values = bucket_key[1:]

            record = {"time_bucket": time_bucket}

            # Add exactly the groupby fields requested
            for field_name, val in zip(groupby_fields, group_values):
                record[field_name] = val

            # Compute aggregated values
            values = {}
            for field, val_list in field_values.items():
                if not val_list:
                    continue
                op = agg_mapping.get(field)
                if not op:
                    continue

                if op == "avg":
                    agg_value = round(mean(val_list), 4)
                elif op == "max":
                    agg_value = round(max(val_list), 4)
                elif op == "min":
                    agg_value = round(min(val_list), 4)
                elif op == "sum":
                    agg_value = round(sum(val_list), 4)
                else:
                    continue

                values[f"{field}--{op}"] = agg_value

            record["values"] = values
            result.append(record)

        return result

