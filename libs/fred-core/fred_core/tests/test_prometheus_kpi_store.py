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
from fred_core.kpi.kpi_writer_structures import KPIEvent, Metric
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
