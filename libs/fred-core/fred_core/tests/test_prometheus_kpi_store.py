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
    Ensure Prometheus labels stay low-cardinality without losing structured dims.

    Why this exists:
    - runtime tool and graph KPI events carry `session_id`, `user_id`, and
      `exchange_id`, but those fields must not become Prometheus label series.

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
            "team_id": "fredlab",
            "session_id": "session-1",
            "user_id": "alice",
            "exchange_id": "exchange-1",
        },
    )

    store.index_event(event)

    resolved_name = store._resolve_metric_name(metric_name)
    label_names = store._label_names[(resolved_name, "timer")]
    assert "tool_name" in label_names
    assert "team_id" in label_names
    assert "session_id" not in label_names
    assert "user_id" not in label_names
    assert "exchange_id" not in label_names
    assert delegate.events == [event]
    assert delegate.events[0].dims["session_id"] == "session-1"
    assert delegate.events[0].dims["user_id"] == "alice"
    assert delegate.events[0].dims["exchange_id"] == "exchange-1"
