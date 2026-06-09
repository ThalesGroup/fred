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

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import cast

import pytest

from fred_core.portable import observability


class _StaticParentSpan(observability.Span):
    def __init__(self, span_id: str) -> None:
        self._span_id = span_id

    @property
    def span_id(self) -> str | None:
        return self._span_id


class _ShutdownAwareTracer(observability.Tracer):
    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.fixture(autouse=True)
def restore_observability_globals() -> Iterator[None]:
    original_tracer = observability.get_tracer()
    original_metrics = observability.get_metrics_provider()
    try:
        yield
    finally:
        observability.set_tracer(original_tracer)
        observability.set_metrics_provider(original_metrics)


def test_logging_tracer_emits_parent_and_runtime_attributes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("fred_core.tests.traces")
    tracer = observability.LoggingTracer(logger=logger)

    with caplog.at_level(logging.INFO, logger=logger.name):
        span = tracer.start_span(
            "agent.run",
            attributes={"agent_id": "demo"},
            parent=_StaticParentSpan("span-123"),
            request_id="req-456",
        )
        span.set_attribute("status", "ok")
        span.end()

    record = caplog.records[-1]
    assert record.message == "trace.span"
    span = cast(dict[str, object], record.__dict__["span"])
    assert span["name"] == "agent.run"
    assert span["attributes"] == {
        "agent_id": "demo",
        "parent_span_id": "span-123",
        "request_id": "req-456",
        "status": "ok",
    }
    assert cast(int, span["duration_ms"]) >= 0


def test_logging_metrics_provider_emits_ok_status_and_groups(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("fred_core.tests.metrics")
    provider = observability.LoggingMetricsProvider(logger=logger)

    with caplog.at_level(logging.INFO, logger=logger.name):
        with provider.timer(
            "tool.call",
            dims={"tool": "search"},
            groups=["chat"],
        ) as dims:
            dims["agent_id"] = "demo"

    record = caplog.records[-1]
    assert record.message == "metrics.timer"
    metric = cast(dict[str, object], record.__dict__["metric"])
    assert metric["name"] == "tool.call"
    assert metric["dims"] == {
        "tool": "search",
        "agent_id": "demo",
        "status": "ok",
    }
    assert metric["groups"] == ["chat"]
    assert cast(float, metric["duration_ms"]) >= 0


def test_logging_metrics_provider_marks_error_before_reraising() -> None:
    provider = observability.LoggingMetricsProvider(
        logger=logging.getLogger("fred_core.tests.metrics.errors")
    )

    with pytest.raises(RuntimeError, match="boom"):
        with provider.timer("tool.call", dims={"tool": "search"}) as dims:
            dims["agent_id"] = "demo"
            raise RuntimeError("boom")


def test_in_memory_metrics_provider_records_ok_and_error_timers() -> None:
    provider = observability.InMemoryMetricsProvider()

    with provider.timer("tool.call", dims={"tool": "search"}) as dims:
        dims["agent_id"] = "demo"

    with pytest.raises(ValueError, match="bad"):
        with provider.timer("tool.call", dims={"tool": "search"}) as dims:
            dims["agent_id"] = "demo"
            raise ValueError("bad")

    timers = provider.timers
    assert len(timers) == 2
    assert timers[0].name == "tool.call"
    assert timers[0].dims == {
        "tool": "search",
        "agent_id": "demo",
        "status": "ok",
    }
    assert timers[0].elapsed_s >= 0
    assert timers[1].dims["status"] == "error"

    provider.clear()
    assert provider.timers == []


def test_global_observability_singletons_can_be_overridden_and_shutdown() -> None:
    tracer = _ShutdownAwareTracer()
    metrics = observability.InMemoryMetricsProvider()

    observability.set_tracer(tracer)
    observability.set_metrics_provider(metrics)

    assert observability.get_tracer() is tracer
    assert observability.get_metrics_provider() is metrics

    observability.shutdown()
    assert tracer.shutdown_called is True
