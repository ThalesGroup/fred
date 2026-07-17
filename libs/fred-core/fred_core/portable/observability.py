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
Portable observability primitives for Fred runtimes.

Why this module exists:
- every Fred runtime (ReAct, Graph, pod factory) needs a common tracing and
  metrics interface that is backend-agnostic and zero-dependency
- callers should not care whether the backend is Langfuse, a log file, or nothing

How to use it:
- use Tracer / MetricsProvider as type annotations in RuntimeServices
- configure the pod-level backend once in observability_factory.py via
  set_tracer() / set_metrics_provider()
- the rest of the runtime calls get_tracer() / get_metrics_provider()

Example:
    tracer = get_tracer()
    span = tracer.start_span("agent.run")
    span.set_attribute("agent_id", agent_id)
    span.end()

    with get_metrics_provider().timer("tool.call", dims={"tool": name}):
        result = await tool.run()
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------


class Span:
    """
    One unit of traced work.

    The base implementation is a no-op — subclasses add backend behaviour.
    Callers always call end() explicitly (the runtime does not use a context
    manager here because span lifetime often crosses await boundaries).
    """

    @property
    def span_id(self) -> str | None:
        """
        Return the backend span identifier when the implementation exposes one.

        Why this exists:
        - some tracing backends can create parent/child relationships only when
          the caller can read a stable span id from the current span

        How to use it:
        - treat `None` as "this backend does not expose parent-linking ids"

        Example:
        - `if span.span_id is not None: trace_context["parent_span_id"] = span.span_id`
        """

        return None

    def set_attribute(self, key: str, value: Any) -> None:
        """Record one key/value attribute on this span."""

    def end(self) -> None:
        """Mark this span as complete."""


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class Tracer:
    """
    Tracing backend.

    The base class is a null tracer — override start_span() to add behaviour.
    Use LoggingTracer for structured log output or plug in a Langfuse adapter.
    """

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: Span | None = None,
        **kwargs: object,
    ) -> Span:
        """Open a new span. Returns a no-op Span by default."""
        return Span()

    def shutdown(self) -> None:
        """Release backend resources. Called once at pod shutdown."""


class LoggingTracer(Tracer):
    """
    Tracer that emits each span as a structured log entry on end().

    Why this exists:
    - gives developers a human-readable trace without requiring Langfuse

    How to use it:
    - set as the pod tracer in observability_factory when langfuse is disabled

    Example:
    - `set_tracer(LoggingTracer())`
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("fred_core.traces")

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: Span | None = None,
        **kwargs: object,
    ) -> Span:
        """
        Open a new logging-backed span.

        Why this exists:
        - runtime code passes structured attributes and optional parent spans
          through one shared tracing seam

        How to use it:
        - pass `attributes=` for the canonical attribute bag
        - optional `parent` contributes `parent_span_id` when available

        Example:
        - `tracer.start_span("agent.run", attributes={"agent_id": "demo"})`
        """

        del context
        combined_attributes: dict[str, object] = dict(attributes or {})
        combined_attributes.update(kwargs)
        parent_span_id = parent.span_id if parent is not None else None
        if parent_span_id is not None:
            combined_attributes.setdefault("parent_span_id", parent_span_id)
        return _LoggingSpan(
            name=name,
            logger=self._logger,
            extra=combined_attributes,
        )


@dataclass
class _LoggingSpan(Span):
    name: str
    logger: logging.Logger
    extra: dict[str, Any] = field(default_factory=dict)
    _attrs: dict[str, Any] = field(default_factory=dict)
    _start: float = field(default_factory=time.time)

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value

    def end(self) -> None:
        self.logger.info(
            "trace.span",
            extra={
                "span": {
                    "name": self.name,
                    "attributes": {**self.extra, **self._attrs},
                    "duration_ms": int((time.time() - self._start) * 1000),
                }
            },
        )


# ---------------------------------------------------------------------------
# MetricsProvider
# ---------------------------------------------------------------------------


class MetricsProvider:
    """
    Metrics backend.

    The base class is a null provider — override timer() to add behaviour.
    Use LoggingMetricsProvider for structured log output or plug in a KPI adapter.
    """

    @contextmanager
    def timer(
        self,
        name: str,
        *,
        dims: dict[str, str | None] | None = None,
    ) -> Generator[dict[str, str | None], None, None]:
        """Time a block. Yields a mutable dims dict callers can annotate."""
        yield dict(dims) if dims else {}


class LoggingMetricsProvider(MetricsProvider):
    """
    MetricsProvider that logs each timer as a structured entry.

    Why this exists:
    - gives developers visible timing without requiring a metrics backend

    How to use it:
    - set as the pod metrics provider in observability_factory

    Example:
    - `set_metrics_provider(LoggingMetricsProvider())`
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("fred_core.metrics")

    @contextmanager
    def timer(
        self,
        name: str,
        *,
        dims: dict[str, str | None] | None = None,
    ) -> Generator[dict[str, str | None], None, None]:
        import time as _time

        d: dict[str, str | None] = dict(dims) if dims else {}
        start = _time.perf_counter()
        try:
            yield d
        except Exception:
            d.setdefault("status", "error")
            raise
        finally:
            d.setdefault("status", "ok")
            self._logger.info(
                "metrics.timer",
                extra={
                    "metric": {
                        "name": name,
                        "dims": d,
                        "duration_ms": round((_time.perf_counter() - start) * 1000, 2),
                    }
                },
            )


@dataclass
class TimerRecord:
    """One captured timer entry from InMemoryMetricsProvider."""

    name: str
    dims: dict[str, str | None]
    elapsed_s: float = 0.0


class InMemoryMetricsProvider(MetricsProvider):
    """
    MetricsProvider that stores timer records in memory for test assertions.

    Why this exists:
    - tests need to assert that specific timers were emitted with correct dims
    - keeping it here avoids duplicating the implementation in every test suite

    How to use it:
    - pass as RuntimeServices(metrics=InMemoryMetricsProvider())
    - inspect .timers after the call under test

    Example:
    - `metrics = InMemoryMetricsProvider(); assert metrics.timers[0].name == "tool.call"`
    """

    def __init__(self) -> None:
        self._timers: list[TimerRecord] = []

    @property
    def timers(self) -> list[TimerRecord]:
        return list(self._timers)

    def clear(self) -> None:
        self._timers.clear()

    @contextmanager
    def timer(
        self,
        name: str,
        *,
        dims: dict[str, str | None] | None = None,
    ) -> Generator[dict[str, str | None], None, None]:
        import time as _time

        d: dict[str, str | None] = dict(dims) if dims else {}
        start = _time.perf_counter()
        try:
            yield d
        except Exception:
            d.setdefault("status", "error")
            raise
        finally:
            elapsed_s = _time.perf_counter() - start
            d.setdefault("status", "ok")
            self._timers.append(
                TimerRecord(name=name, dims=dict(d), elapsed_s=elapsed_s)
            )


# ---------------------------------------------------------------------------
# Global pod-level singletons
# ---------------------------------------------------------------------------
# Configured once at startup by observability_factory; read everywhere else.

_tracer: Tracer = Tracer()
_metrics: MetricsProvider = MetricsProvider()


def set_tracer(tracer: Tracer) -> None:
    """Configure the pod-level tracer. Call once at startup."""
    global _tracer
    _tracer = tracer


def get_tracer() -> Tracer:
    """Return the pod-level tracer (null tracer if not configured)."""
    return _tracer


def set_metrics_provider(provider: MetricsProvider) -> None:
    """Configure the pod-level metrics provider. Call once at startup."""
    global _metrics
    _metrics = provider


def get_metrics_provider() -> MetricsProvider:
    """Return the pod-level metrics provider (null provider if not configured)."""
    return _metrics


def shutdown() -> None:
    """Shut down the pod-level tracer. Call once at pod shutdown."""
    _tracer.shutdown()
