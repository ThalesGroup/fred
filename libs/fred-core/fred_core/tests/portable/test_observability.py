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


def test_no_tracer_captures_content_by_default() -> None:
    """
    The switch that makes the content exclusion of
    `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §7 auditable: with every
    built-in backend answering False, no stream can carry content whatever the
    call sites do.
    """

    assert observability.Tracer().captures_content is False
    assert observability.LoggingTracer().captures_content is False


def test_logging_span_records_content_sizes_but_never_the_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    This logger feeds the generic app-log store, which carries no content.
    A caller that ignores `captures_content` still must not leak into it.
    """

    logger = logging.getLogger("fred_core.tests.traces.io")
    tracer = observability.LoggingTracer(logger=logger)

    with caplog.at_level(logging.INFO, logger=logger.name):
        span = tracer.start_span("v2.react.model")
        span.set_io(input="a secret question", output="a secret answer")
        span.end()

    attributes = cast(
        dict[str, object],
        cast(dict[str, object], caplog.records[-1].__dict__["span"])["attributes"],
    )
    assert attributes == {"input_chars": 17, "output_chars": 15}
    assert "secret" not in caplog.text


def test_logging_span_records_usage_in_full(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Token counts and cost are measurement, not content — safe to log whole."""

    logger = logging.getLogger("fred_core.tests.traces.usage")
    tracer = observability.LoggingTracer(logger=logger)

    with caplog.at_level(logging.INFO, logger=logger.name):
        span = tracer.start_span("v2.react.model")
        span.set_usage(
            model="gpt-4o", usage={"input": 812, "output": 96}, cost={"total": 0.02}
        )
        span.end()

    attributes = cast(
        dict[str, object],
        cast(dict[str, object], caplog.records[-1].__dict__["span"])["attributes"],
    )
    assert attributes == {
        "model_name": "gpt-4o",
        "usage_input": 812,
        "usage_output": 96,
        "cost_total": 0.02,
    }


def test_null_span_accepts_io_and_usage_without_effect() -> None:
    """Every call site may call these unconditionally against any backend."""

    span = observability.Tracer().start_span("agent.stream")
    span.set_io(input="x", output="y")
    span.set_usage(model="m", usage={"input": 1}, cost={"total": 1.0})
    span.end()


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


def test_logging_metrics_provider_emits_ok_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("fred_core.tests.metrics")
    provider = observability.LoggingMetricsProvider(logger=logger)

    with caplog.at_level(logging.INFO, logger=logger.name):
        with provider.timer(
            "tool.call",
            dims={"tool": "search"},
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
