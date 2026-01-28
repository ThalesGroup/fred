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


_DEFAULT_DIM_LABELS: Tuple[str, ...] = (
    "env",
    "cluster",
    "actor_type",
    "user_id",
    "groups",
    "status",
    "http_status",
    "error_code",
    "exception_type",
    "route",
    "method",
    "scope_type",
    "scope_id",
    "exchange_id",
    "agent_id",
    "model",
    "doc_uid",
    "doc_source",
    "file_type",
    "index",
    "tool_name",
    "agent_step",
    "policy",
    "step",
    "source",
)


def _sanitize_label_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if not safe or safe[0].isdigit():
        safe = f"dim_{safe}"
    return safe


class PrometheusKPIStore(BaseKPIStore):
    """
    Prometheus-backed KPI sink.

    - Converts KPI events into Prometheus counters/gauges/histograms.
    - Optionally delegates to a primary store for persistence/query.
    """

    def __init__(self, delegate: Optional[BaseKPIStore] = None):
        self._delegate = delegate
        self._metrics: Dict[Tuple[str, str], Counter | Gauge | Histogram] = {}
        self._label_maps: Dict[Tuple[str, str], Dict[str, str]] = {}
        self._label_names: Dict[Tuple[str, str], Tuple[str, ...]] = {}
        self._metric_name_map: Dict[str, str] = {}
        self._lock = threading.Lock()

    def _resolve_metric_name(self, raw_name: str) -> str:
        base_name = _sanitize_metric_name(raw_name)
        cached = self._metric_name_map.get(base_name)
        if cached is not None:
            return cached

        existing = getattr(REGISTRY, "_names_to_collectors", {})
        resolved = base_name
        if resolved in existing:
            candidate = f"kpi_{resolved}"
            while candidate in existing:
                candidate = f"kpi_{candidate}"
            logger.warning(
                "[KPI][prometheus] Metric name '%s' collides with existing collector; "
                "using '%s' instead.",
                base_name,
                candidate,
            )
            resolved = candidate
        self._metric_name_map[base_name] = resolved
        return resolved

    def ensure_ready(self) -> None:
        if self._delegate:
            self._delegate.ensure_ready()

    def _get_metric(
        self, name: str, metric_type: str, label_names: Tuple[str, ...]
    ) -> Counter | Gauge | Histogram:
        key = (name, metric_type)
        with self._lock:
            existing = self._metrics.get(key)
            if existing is not None:
                return existing
            if metric_type == "counter":
                metric = Counter(
                    name, "KPI counter", list(label_names), registry=REGISTRY
                )
            elif metric_type == "gauge":
                metric = Gauge(name, "KPI gauge", list(label_names), registry=REGISTRY)
            else:
                metric = Histogram(
                    name, "KPI timer", list(label_names), registry=REGISTRY
                )
            self._metrics[key] = metric
            return metric

    def _emit_value(
        self,
        metric_name: str,
        metric_type: str,
        value: float,
        label_values: Dict[str, str],
    ):
        label_names = self._label_names[(metric_name, metric_type)]
        metric = self._get_metric(metric_name, metric_type, label_names)
        if metric_type == "counter":
            if value < 0:
                logger.warning(
                    "[KPI][prometheus] Skipping negative counter: %s=%s",
                    metric_name,
                    value,
                )
                return
            cast(Counter, metric).labels(**label_values).inc(value)
        elif metric_type == "gauge":
            cast(Gauge, metric).labels(**label_values).set(value)
        else:
            cast(Histogram, metric).labels(**label_values).observe(value)

    def _resolve_labeling(
        self, metric_name: str, metric_type: str, event: KPIEvent
    ) -> Dict[str, str]:
        key = (metric_name, metric_type)
        label_names = self._label_names.get(key)
        label_map = self._label_maps.get(key)
        if label_names is None or label_map is None:
            raw_keys = set(_DEFAULT_DIM_LABELS)
            if event.dims:
                raw_keys.update(event.dims.keys())
            label_map = {}
            for raw_key in sorted(raw_keys):
                safe_key = _sanitize_label_name(raw_key)
                if safe_key not in label_map:
                    label_map[safe_key] = raw_key
            label_names = tuple(label_map.keys())
            self._label_maps[key] = label_map
            self._label_names[key] = label_names
        dims = {k: v for k, v in (event.dims or {}).items() if v is not None}
        label_values: Dict[str, str] = {}
        for safe_key, raw_key in label_map.items():
            value = dims.get(raw_key)
            label_values[safe_key] = "" if value is None else str(value)
        return label_values

    def _set_labeling(
        self,
        metric_name: str,
        metric_type: str,
        label_names: Tuple[str, ...],
        label_map: Dict[str, str],
    ) -> None:
        key = (metric_name, metric_type)
        if key not in self._label_names:
            self._label_names[key] = label_names
            self._label_maps[key] = label_map

    def _record_event(self, event: KPIEvent) -> None:
        if not event.metric or event.metric.value is None:
            return

        base_name = self._resolve_metric_name(event.metric.name)
        metric_type = event.metric.type
        label_values = self._resolve_labeling(base_name, metric_type, event)
        base_label_names = self._label_names[(base_name, metric_type)]
        base_label_map = self._label_maps[(base_name, metric_type)]

        self._emit_value(
            base_name, metric_type, float(event.metric.value), label_values
        )

        if event.cost:
            costs = event.cost.model_dump(exclude_none=True)
            for key, value in costs.items():
                if value is None:
                    continue
                cost_name = f"{base_name}_cost_{_sanitize_metric_name(str(key))}_total"
                self._set_labeling(
                    cost_name, "counter", base_label_names, base_label_map
                )
                self._emit_value(cost_name, "counter", float(value), label_values)

        if event.quantities:
            quantities = event.quantities.model_dump(exclude_none=True)
            for key, value in quantities.items():
                if value is None:
                    continue
                qty_name = (
                    f"{base_name}_quantity_{_sanitize_metric_name(str(key))}_total"
                )
                self._set_labeling(
                    qty_name, "counter", base_label_names, base_label_map
                )
                self._emit_value(qty_name, "counter", float(value), label_values)

    def index_event(self, event: KPIEvent) -> None:
        if self._delegate:
            self._delegate.index_event(event)
        if event.metric and event.metric.name.startswith("process."):
            # Process KPIs are already exported by the Prometheus client; keep them in
            # the KPI pipeline (logs/OpenSearch) but skip Prometheus to avoid clashes.
            return
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
