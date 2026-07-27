# Copyright Thales 2026
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
Tests for PrometheusKPIStore label cardinality and dimension handling.

Ref: docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §3.1 — Prometheus/Grafana
     labels are an explicit allow-list (PROMETHEUS_ALLOWED_LABELS), not a
     deny-list: team_id and agent_instance_id are deliberately excluded
     (OBSERV-02's ReBAC-scoped presets already answer "usage by team/agent"),
     not just user_id/session_id/exchange_id.
"""

from __future__ import annotations

from uuid import uuid4

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer_structures import KPIEvent, Metric, Trace
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore


class _RecordingKPIStore(BaseKPIStore):
    """Capture delegated KPI events for offline Prometheus store tests."""

    def __init__(self) -> None:
        """Initialize the in-memory event list used by assertions."""
        self.events: list[KPIEvent] = []

    def ensure_ready(self) -> None:
        """Satisfy the KPI store contract without external infrastructure."""
        return None

    def index_event(self, event: KPIEvent) -> None:
        """Record one delegated event exactly as received."""
        self.events.append(event)

    def bulk_index(self, events: list[KPIEvent]) -> None:
        """Record a batch of delegated events exactly as received."""
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        """Return an empty query result because assertions inspect captured events."""
        return KPIQueryResult(rows=[])


def test_prometheus_store_filters_unbounded_identity_labels_for_scrape() -> None:
    """
    Ensure Prometheus labels stay low-cardinality and RGPD-safe, without
    losing structured dims on the delegate (OpenSearch) store.

    Why this exists:
    - runtime tool and graph KPI events carry `session_id`, `user_id`,
      `exchange_id`, `team_id`, `agent_instance_id`, `trace_id`,
      `correlation_id`, and `checkpoint_id` — none of those must become
      Prometheus label series (see PROMETHEUS_ALLOWED_LABELS for why each
      one specifically is excluded).
    - `tool_name` and `template_agent_id` (the catalog blueprint, not a
      team's configured instance) are legitimate operational-health labels
      and must still pass through.

    How to use it:
    - run in the default offline `fred-core` test suite.

    Example:
    - `pytest fred_core/tests/test_prometheus_kpi_store.py -q`
    """
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.prometheus_identity_filter_{uuid4().hex}"
    event = KPIEvent(
        metric=Metric(name=metric_name, type="timer", value=12.0, unit="ms"),
        dims={
            "tool_name": "search",
            "template_agent_id": "customer-support-bot",
            "team_id": "fredlab",
            "agent_instance_id": "instance-1",
            "session_id": "session-1",
            "user_id": "alice",
            "exchange_id": "exchange-1",
            "trace_id": "trace-1",
            "correlation_id": "correlation-1",
            "checkpoint_id": "checkpoint-1",
        },
    )

    store.index_event(event)

    resolved_name = store._resolve_metric_name(metric_name)
    label_names = store._label_names[(resolved_name, "timer")]
    assert "tool_name" in label_names
    assert "template_agent_id" in label_names
    assert "team_id" not in label_names
    assert "agent_instance_id" not in label_names
    assert "session_id" not in label_names
    assert "user_id" not in label_names
    assert "exchange_id" not in label_names
    assert "trace_id" not in label_names
    assert "correlation_id" not in label_names
    assert "checkpoint_id" not in label_names
    # The delegate (OpenSearch, backing OBSERV-02's ReBAC-scoped analytics)
    # still receives every dim, full fidelity — filtering is Prometheus-only.
    assert delegate.events == [event]
    assert delegate.events[0].dims["team_id"] == "fredlab"
    assert delegate.events[0].dims["session_id"] == "session-1"
    assert delegate.events[0].dims["user_id"] == "alice"
    assert delegate.events[0].dims["exchange_id"] == "exchange-1"


def test_prometheus_store_filters_generic_phase_and_operation_dims() -> None:
    """
    The generic `phase` (app.phase_latency_ms — Graph, checkpoint SQL, KF) and
    `operation` (e.g. llm.call_latency_ms) dims stay excluded: their value sets
    are wide and shared across unrelated call sites. TURN-01's three pre-LLM
    stages and five OpenFGA operations use the dedicated, closed-set
    `runtime_stage`/`rebac_operation` labels instead (see the tests below) —
    `phase`/`operation` themselves are never promoted.
    """
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.generic_dim_filter_{uuid4().hex}"
    event = KPIEvent(
        metric=Metric(name=metric_name, type="timer", value=3.0, unit="ms"),
        dims={"phase": "planning", "operation": "check", "status": "ok"},
    )

    store.index_event(event)

    resolved_name = store._resolve_metric_name(metric_name)
    label_names = store._label_names[(resolved_name, "timer")]
    assert "phase" not in label_names
    assert "operation" not in label_names
    assert "status" in label_names


def test_prometheus_store_promotes_runtime_stage_and_rebac_operation() -> None:
    """
    TURN-01 Grafana-visibility fix: `runtime_stage` (runtime.stage_latency_ms)
    and `rebac_operation` (rebac.call_latency_ms/call_total) are the two
    dedicated, closed-set dims deliberately promoted to Prometheus labels so
    Grafana can distinguish pod_authz/runtime_binding/runtime_binding_internal
    and check/list_objects/list_users/write/read.
    """
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.runtime_stage_promotion_{uuid4().hex}"
    event = KPIEvent(
        metric=Metric(name=metric_name, type="timer", value=3.0, unit="ms"),
        dims={
            "runtime_stage": "pod_authz",
            "rebac_operation": "check",
            "status": "ok",
            "service": "fred-runtime",
        },
    )

    store.index_event(event)

    resolved_name = store._resolve_metric_name(metric_name)
    label_names = store._label_names[(resolved_name, "timer")]
    assert "runtime_stage" in label_names
    assert "rebac_operation" in label_names
    assert "status" in label_names
    assert "service" in label_names


def test_prometheus_store_gives_each_runtime_stage_value_a_distinct_series() -> None:
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.runtime_stage_series_{uuid4().hex}"

    for stage in ("pod_authz", "runtime_binding", "runtime_binding_internal"):
        store.index_event(
            KPIEvent(
                metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
                dims={"runtime_stage": stage},
            )
        )

    resolved_name = store._resolve_metric_name(metric_name)
    metric = store._metrics[(resolved_name, "timer")]
    samples = {
        s.labels["runtime_stage"]
        for s in next(iter(metric.collect())).samples
        if "runtime_stage" in s.labels
    }
    assert samples == {"pod_authz", "runtime_binding", "runtime_binding_internal"}


def test_prometheus_store_gives_each_rebac_operation_value_a_distinct_series() -> None:
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.rebac_operation_series_{uuid4().hex}"

    for operation in ("check", "list_objects", "list_users", "write", "read"):
        store.index_event(
            KPIEvent(
                metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
                dims={"rebac_operation": operation},
            )
        )

    resolved_name = store._resolve_metric_name(metric_name)
    metric = store._metrics[(resolved_name, "timer")]
    samples = {
        s.labels["rebac_operation"]
        for s in next(iter(metric.collect())).samples
        if "rebac_operation" in s.labels
    }
    assert samples == {"check", "list_objects", "list_users", "write", "read"}


def test_prometheus_store_label_schema_is_stable_regardless_of_arrival_order() -> None:
    """
    Prometheus requires a fixed label set per metric name/type. Emitting the
    three runtime_stage values (or five rebac_operation values) in any order
    must resolve to the same label schema — not a schema that depends on
    which dims the first event happened to carry.
    """
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.label_schema_order_{uuid4().hex}"

    order_a = ["runtime_binding_internal", "pod_authz", "runtime_binding"]
    for stage in order_a:
        store.index_event(
            KPIEvent(
                metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
                dims={"runtime_stage": stage},
            )
        )
    resolved_name = store._resolve_metric_name(metric_name)
    label_names_a = store._label_names[(resolved_name, "timer")]

    # A second, freshly-ordered store must resolve to the identical schema.
    delegate_b = _RecordingKPIStore()
    store_b = PrometheusKPIStore(delegate=delegate_b)
    for stage in reversed(order_a):
        store_b.index_event(
            KPIEvent(
                metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
                dims={"runtime_stage": stage},
            )
        )
    resolved_name_b = store_b._resolve_metric_name(metric_name)
    label_names_b = store_b._label_names[(resolved_name_b, "timer")]

    assert label_names_a == label_names_b


def test_prometheus_store_trace_id_never_becomes_a_label_even_when_set() -> None:
    """
    Item B: trace.trace_id must survive to the OpenSearch delegate (for
    joining runtime_binding/runtime_binding_internal across the pod/
    control-plane boundary) but never leak into Prometheus labels — trace is a
    structurally separate field from dims, never read by the label filter.
    """
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.trace_id_isolation_{uuid4().hex}"
    event = KPIEvent(
        metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
        dims={"runtime_stage": "runtime_binding"},
        trace=Trace(trace_id="corr-shared-123"),
    )

    store.index_event(event)

    assert delegate.events[0].trace is not None
    assert delegate.events[0].trace.trace_id == "corr-shared-123"
    resolved_name = store._resolve_metric_name(metric_name)
    label_names = store._label_names[(resolved_name, "timer")]
    assert "trace_id" not in label_names
    assert "trace" not in label_names


def test_prometheus_store_never_promotes_any_identity_label() -> None:
    """
    Item D: explicit, exhaustive privacy test — none of these identifiers may
    ever become a Prometheus label, even alongside the newly-promoted
    runtime_stage/rebac_operation dims.
    """
    forbidden = {
        "trace_id",
        "correlation_id",
        "request_id",
        "user_id",
        "session_id",
        "team_id",
        "agent_id",
        "agent_instance_id",
        "checkpoint_id",
    }
    delegate = _RecordingKPIStore()
    store = PrometheusKPIStore(delegate=delegate)
    metric_name = f"test.identity_privacy_{uuid4().hex}"
    dims: dict[str, str | None] = {name: f"value-{name}" for name in forbidden}
    dims["runtime_stage"] = "pod_authz"
    dims["rebac_operation"] = "check"
    event = KPIEvent(
        metric=Metric(name=metric_name, type="timer", value=1.0, unit="ms"),
        dims=dims,
    )

    store.index_event(event)

    resolved_name = store._resolve_metric_name(metric_name)
    label_names = set(store._label_names[(resolved_name, "timer")])
    assert label_names.isdisjoint(forbidden)
    assert "runtime_stage" in label_names
    assert "rebac_operation" in label_names
