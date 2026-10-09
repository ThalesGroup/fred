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
What a Knowledge Base pod tells the people operating the platform.

Operational metrics only — Stream 1 of OBSERVABILITY-AND-AUDIT.md. The series,
their labels and their values are a contract shared with every other SDK
implementation: openspec/specs/knowledge-base-pod-metrics/spec.md. Every series
is labelled by the pod's `service` (its `app.runtime_id`, chosen at deployment,
the same value its log records carry) and by the Knowledge Base *definition* it
serves, never by a team, an instance, a library or a run: "how is my folder doing" is a team's question,
answered inside Fred under Fred's own access control, and a scraped label is
visible to everyone with Grafana. That is the whole reason no identifier of a
run or of its owner is accepted here.

An author writes none of this. The activity observes every run, and the SDK's
own clients observe every call to Fred, so a Knowledge Base that writes only
its handler is measured exactly like one that does far more.

`prometheus_client` ships with the `knowledge-base` extra, beside the workflow
engine. Without it every function here does nothing: a developer tool calling a
`DocumentPublisher` with no worker around it has nobody to be scraped by.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx
from fred_pod.common.structures import KpiPrometheusSinkConfig

if TYPE_CHECKING:
    from fred_sdk.knowledge_base.knowledge_base import KnowledgeBase
    from fred_sdk.knowledge_base.models import KnowledgeBaseSyncResult

logger = logging.getLogger(__name__)

# A run is bounded by the activity's six hours; a call by its client's timeout.
_RUN_BUCKETS = (1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 14400, 21600)
_INGESTION_BUCKETS = (1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800)
_CALL_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 180)

# Issue codes are the author's own strings. They are meant to be a small,
# stable vocabulary, but nothing forces one; past this many distinct codes a
# new one is counted as `other` rather than growing the series without bound.
MAX_ISSUE_CODES = 100
_OTHER_CODE = "other"

# Until `bind` names the pod and its definition, which `serve` does before
# polling. A series under this label is a call made outside a worker.
_UNBOUND = "unbound"

# The `sdk` label of `fred_kb_info`: which implementation of the contract this
# is, since each numbers its own releases.
SDK_NAME = "fred-sdk-python"


class MetricsEndpointUnavailable(RuntimeError):
    """The enabled metrics endpoint could not be opened — its port is taken."""


class _Instruments:
    """Every series this pod exports, registered once per process."""

    def __init__(self) -> None:
        from prometheus_client import Counter, Gauge, Histogram

        kb = ("service", "knowledge_base")
        self.info = Gauge(
            "fred_kb_info",
            "The Knowledge Base definition this pod serves; always 1.",
            [*kb, "version", "sdk", "sdk_version"],
        )
        self.runs_in_progress = Gauge(
            "fred_kb_runs_in_progress",
            "Synchronization runs this pod is serving right now.",
            kb,
        )
        self.runs = Counter(
            "fred_kb_runs",
            "Synchronization runs served, one per attempt. `outcome` is what the "
            "handler reported, `error` when it or the SDK raised, `interrupted` "
            "when the worker was stopped mid-run. `reconciliation` is the run's "
            "own: complete, partial or up_to_date, none when it did not report.",
            [*kb, "outcome", "reconciliation"],
        )
        self.run_duration = Histogram(
            "fred_kb_run_duration_seconds",
            "Wall time of one run attempt, from its configuration fetch to its end.",
            [*kb, "outcome"],
            buckets=_RUN_BUCKETS,
        )
        self.last_run = Gauge(
            "fred_kb_last_run_timestamp_seconds",
            "When this pod last finished a run with this outcome (Unix time).",
            [*kb, "outcome"],
        )
        self.run_errors = Counter(
            "fred_kb_run_errors",
            "Runs that raised instead of reporting, by where and what.",
            [*kb, "stage", "exception_type"],
        )
        self.items = Counter(
            "fred_kb_items",
            "Items runs reported, by what happened to them. `discovered` and "
            "`unchanged` are counted on every run that sees them.",
            [*kb, "change"],
        )
        self.issues = Counter(
            "fred_kb_issues",
            "Warnings and errors runs reported, by their stable code.",
            [*kb, "severity", "code"],
        )
        self.requests = Counter(
            "fred_kb_requests",
            "Calls this pod made to Fred, by service, operation and status class.",
            [*kb, "target", "operation", "status"],
        )
        self.request_duration = Histogram(
            "fred_kb_request_duration_seconds",
            "Duration of one call to Fred, transport errors included.",
            [*kb, "target", "operation"],
            buckets=_CALL_BUCKETS,
        )
        self.ingestion_wait = Histogram(
            "fred_kb_ingestion_wait_seconds",
            "How long a written document took to reach a terminal ingestion "
            "state, or `timeout` when the wait gave up first.",
            [*kb, "state"],
            buckets=_INGESTION_BUCKETS,
        )


_instruments: _Instruments | None = None
_available = True
_service = _UNBOUND
_knowledge_base = _UNBOUND
_issue_codes: set[str] = set()


def _get() -> _Instruments | None:
    global _instruments, _available
    if _instruments is None and _available:
        try:
            _instruments = _Instruments()
        except ModuleNotFoundError:
            _available = False
    return _instruments


def bind(knowledge_base: KnowledgeBase, runtime_id: str) -> None:
    """Name the pod and the definition every later series is labelled with."""
    global _service, _knowledge_base
    _service = runtime_id
    _knowledge_base = knowledge_base.id
    instruments = _get()
    if instruments is not None:
        instruments.info.labels(
            runtime_id,
            knowledge_base.id,
            knowledge_base.version,
            SDK_NAME,
            _sdk_version(),
        ).set(1)


def _identity() -> tuple[str, str]:
    """The two labels every series opens with, read once per observation."""
    return _service, _knowledge_base


def start_exporter(config: KpiPrometheusSinkConfig) -> bool:
    """Serve `/metrics` when configured to. Returns whether it is served."""
    if not config.enabled:
        return False
    if _get() is None:
        logger.warning(
            "Metrics are enabled but prometheus_client is not installed: "
            "install fred-sdk[knowledge-base]"
        )
        return False
    from prometheus_client import start_http_server

    try:
        start_http_server(config.port, addr=config.address)
    except OSError as error:
        # A deployment mistake, not a measurement one: say where, and stop the
        # pod before it serves a run nobody can see.
        raise MetricsEndpointUnavailable(
            f"Cannot serve metrics on {config.address}:{config.port}: {error}. "
            "Choose another observability.kpi.prometheus.port, or disable it."
        ) from error
    logger.info("Knowledge Base metrics served at %s:%s", config.address, config.port)
    return True


class RunObservation:
    """One run attempt, from the moment it is picked up to its end."""

    def __init__(self) -> None:
        self.stage = "context"
        self.result: KnowledgeBaseSyncResult | None = None


@contextmanager
def observing_run() -> Iterator[RunObservation]:
    """Measure the run inside; advance `stage` as it goes, set `result` at its end.

    Whatever escapes is re-raised untouched — Temporal decides what a raise
    means — and counted once, under the stage it escaped from.
    """
    observation = RunObservation()
    instruments = _get()
    if instruments is None:
        yield observation
        return

    kb = _identity()
    started = time.monotonic()
    instruments.runs_in_progress.labels(*kb).inc()
    outcome, reconciliation = "error", "none"
    try:
        yield observation
        if observation.result is not None:
            outcome = observation.result.outcome.value
            reconciliation = observation.result.reconciliation.value
            _count_result(instruments, kb, observation.result)
    except asyncio.CancelledError:
        # The worker stopping, or Fred withdrawing the run: neither is the
        # handler failing, and a dashboard should not say so.
        outcome = "interrupted"
        raise
    except BaseException as error:
        instruments.run_errors.labels(
            *kb, observation.stage, type(error).__name__
        ).inc()
        raise
    finally:
        instruments.runs_in_progress.labels(*kb).dec()
        instruments.runs.labels(*kb, outcome, reconciliation).inc()
        instruments.run_duration.labels(*kb, outcome).observe(
            time.monotonic() - started
        )
        instruments.last_run.labels(*kb, outcome).set_to_current_time()


def _count_result(
    instruments: _Instruments, kb: tuple[str, str], result: KnowledgeBaseSyncResult
) -> None:
    for change in ("discovered", "created", "updated", "removed", "unchanged"):
        count = getattr(result, change)
        if count:
            instruments.items.labels(*kb, change).inc(count)
    for severity, totals in result.issue_counts.items():
        for code, count in totals.items():
            instruments.issues.labels(*kb, severity, _bounded_code(code)).inc(count)


def _bounded_code(code: str) -> str:
    if code in _issue_codes:
        return code
    if len(_issue_codes) >= MAX_ISSUE_CODES:
        return _OTHER_CODE
    _issue_codes.add(code)
    return code


@contextmanager
def observing_request(target: str, operation: str) -> Iterator[Callable[[int], None]]:
    """Measure one call to Fred; call the yielded function with its status code.

    Counted by status class — a dashboard sums `5xx`, not 502 and 503 apart. A
    call that never got an answer is `transport_error` when the network failed
    it, `error` otherwise.
    """
    instruments = _get()
    if instruments is None:
        yield lambda _status: None
        return

    kb = _identity()
    status = "error"

    def answered(code: int) -> None:
        nonlocal status
        status = f"{code // 100}xx"

    started = time.monotonic()
    try:
        yield answered
    except httpx.TransportError:
        status = "transport_error"
        raise
    finally:
        instruments.request_duration.labels(*kb, target, operation).observe(
            time.monotonic() - started
        )
        instruments.requests.labels(*kb, target, operation, status).inc()


def observe_ingestion_wait(state: str, seconds: float) -> None:
    """One document's wait for its ingestion, ended in `state` or `timeout`."""
    instruments = _get()
    if instruments is not None:
        instruments.ingestion_wait.labels(*_identity(), state).observe(seconds)


def _sdk_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("fred-sdk")
    except PackageNotFoundError:
        return "unknown"
