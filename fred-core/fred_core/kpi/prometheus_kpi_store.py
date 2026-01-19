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

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional, Tuple, cast

from prometheus_client import REGISTRY, Counter, Gauge, Histogram

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer_structures import KPIEvent

logger = logging.getLogger(__name__)


def _sanitize_metric_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if not safe or safe[0].isdigit():
        safe = f"kpi_{safe}"
    return safe


def _dims_label_value(event: KPIEvent) -> str:
    dims = {k: v for k, v in (event.dims or {}).items() if v is not None}
    if not dims:
        return ""
    parts = [f"{key}={dims[key]}" for key in sorted(dims.keys())]
    return "|".join(parts)


class PrometheusKPIStore(BaseKPIStore):
    """
    Prometheus-backed KPI sink.

    - Converts KPI events into Prometheus counters/gauges/histograms.
    - Optionally delegates to a primary store for persistence/query.
    """

    def __init__(self, delegate: Optional[BaseKPIStore] = None):
        self._delegate = delegate
        self._metrics: Dict[Tuple[str, str], Counter | Gauge | Histogram] = {}
        self._lock = threading.Lock()

    def ensure_ready(self) -> None:
        if self._delegate:
            self._delegate.ensure_ready()

    def _get_metric(self, name: str, metric_type: str) -> Counter | Gauge | Histogram:
        key = (name, metric_type)
        with self._lock:
            existing = self._metrics.get(key)
            if existing is not None:
                return existing
            if metric_type == "counter":
                metric = Counter(name, "KPI counter", ["dims"], registry=REGISTRY)
            elif metric_type == "gauge":
                metric = Gauge(name, "KPI gauge", ["dims"], registry=REGISTRY)
            else:
                metric = Histogram(name, "KPI timer", ["dims"], registry=REGISTRY)
            self._metrics[key] = metric
            return metric

    def _emit_value(self, metric_name: str, metric_type: str, value: float, dims: str):
        metric = self._get_metric(metric_name, metric_type)
        if metric_type == "counter":
            if value < 0:
                logger.warning(
                    "[KPI][prometheus] Skipping negative counter: %s=%s",
                    metric_name,
                    value,
                )
                return
            cast(Counter, metric).labels(dims=dims).inc(value)
        elif metric_type == "gauge":
            cast(Gauge, metric).labels(dims=dims).set(value)
        else:
            cast(Histogram, metric).labels(dims=dims).observe(value)

    def _record_event(self, event: KPIEvent) -> None:
        if not event.metric or event.metric.value is None:
            return

        dims = _dims_label_value(event)
        base_name = _sanitize_metric_name(event.metric.name)
        metric_type = event.metric.type

        self._emit_value(base_name, metric_type, float(event.metric.value), dims)

        if event.cost:
            costs = event.cost.model_dump(exclude_none=True)
            for key, value in costs.items():
                if value is None:
                    continue
                cost_name = f"{base_name}_cost_{_sanitize_metric_name(str(key))}_total"
                self._emit_value(cost_name, "counter", float(value), dims)

        if event.quantities:
            quantities = event.quantities.model_dump(exclude_none=True)
            for key, value in quantities.items():
                if value is None:
                    continue
                qty_name = (
                    f"{base_name}_quantity_{_sanitize_metric_name(str(key))}_total"
                )
                self._emit_value(qty_name, "counter", float(value), dims)

    def index_event(self, event: KPIEvent) -> None:
        if self._delegate:
            self._delegate.index_event(event)
        self._record_event(event)

    def bulk_index(self, events: list[KPIEvent]) -> None:
        if self._delegate:
            self._delegate.bulk_index(events)
        for event in events:
            self._record_event(event)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        if self._delegate:
            return self._delegate.query(q)
        return KPIQueryResult(rows=[])
