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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_writer_structures import (
    Cost,
    Dims,
    KPIActor,
    KPIEvent,
    Metric,
    MetricType,
    Quantities,
    Trace,
)
from fred_core.security.structure import KeycloakUser

logger = logging.getLogger(__name__)


# -------------------------
# Defaults & DI container
# -------------------------
@dataclass(frozen=True)
class KPIDefaults:
    """
    Default tags and metadata injected into every KPI event.

    Why this exists in Fred:
    - We want dashboards and costs to slice by environment/cluster/source consistently.
    - Teams shouldn’t repeat the same tagging logic everywhere.
    - Static business tags (e.g., tenant/bu) can be attached once at boot.

    Fields:
      - source: human-readable emitter identity and version (e.g. "agentic-backend@0.9.3")
      - env: deployment environment ("dev", "prod", …)
      - cluster: optional cluster label for multi-cluster observability
      - static_dims: arbitrary extra dimensions merged into all events
    """

    source: Optional[str] = None  # e.g. "agentic-backend@0.9.3"
    env: Optional[str] = None  # "dev" | "prod" | ...
    cluster: Optional[str] = None  # optional
    static_dims: Optional[Dims] = None  # merged into every event


def _merge_dims(defaults: KPIDefaults | None, dims: Optional[Dims]) -> Dims:
    """
    Merge global defaults with per-call dimensions, with call-site keys winning.

    Rationale:
    - Ensures every event carries core routing tags (env/cluster/source).
    - Preserves developer intent by letting explicit dims override defaults.
    """
    out: Dims = {}
    if defaults:
        if defaults.env:
            out["env"] = defaults.env
        if defaults.cluster:
            out["cluster"] = defaults.cluster
        if defaults.static_dims:
            out.update({k: v for k, v in defaults.static_dims.items() if v is not None})
    if dims:
        out.update({k: v for k, v in dims.items() if v is not None})
    return out


def _now_iso() -> str:
    """UTC timestamp (ISO 8601). Useful when an explicit @timestamp is required."""
    return datetime.now(timezone.utc).isoformat()


def to_kpi_actor(user: KeycloakUser) -> KPIActor:
    """
    Convert an authenticated Keycloak user into a KPIActor.

    Why:
    - Fred’s KPI model is actor-centric (human/agent/system). We always attribute
      costs and usage to an actor to support per-user chargeback and audits.
    """
    return KPIActor(type="human", user_id=user.uid)


# -------------------------
# Public KPI API (emission)
# -------------------------
class KPIWriter:
    """
    Lean, clean emission API on top of a BaseKPIStore.

    Architectural role in Fred:
    - Single choke-point to enforce metric schema, naming, and error taxonomy.
    - Hides storage specifics (OpenSearch, Prometheus, …) behind BaseKPIStore.
    - Requires an `actor` for every emission → analytics stay attributable.

    Usage:
      kpi = KPIWriter(store, KPIDefaults(env="prod", source="agentic-backend@0.9.3"))
      kpi.count("doc.used_total", actor=actor, dims={"doc_uid": "..."})
    """

    def __init__(self, store: BaseKPIStore, defaults: Optional[KPIDefaults] = None):
        self.store = store
        self.defaults = defaults or KPIDefaults()
        # We attempt to ready the underlying sink but never fail the app on metrics init.
        try:
            self.store.ensure_ready()
        except Exception as e:
            logger.warning(f"[KPI] ensure_ready failed (continuing best-effort): {e}")

    # ---- generic emit --------------------------------------------------------
    def emit(
        self,
        *,
        name: str,
        type: MetricType,
        value: Optional[float] = None,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        cost: Optional[Dict[str, Any]] = None,
        quantities: Optional[Dict[str, Any]] = None,
        labels: Optional[Iterable[str]] = None,
        trace: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        actor: KPIActor,
    ) -> None:
        """
        Core primitive to index a KPIEvent.

        Why enforce this path:
        - Injects actor identity into dims automatically (cannot be bypassed).
        - Centralizes construction of Metric/Cost/Quantities/Trace for schema stability.
        - Applies default dims (env/cluster/source) consistently to every event.
        """
        # Inject actor into dims (cannot be overridden by callers)
        _dims = dict(dims or {})
        _dims["actor_type"] = actor.type
        if actor.user_id:
            _dims["user_id"] = actor.user_id
        merged_dims = _merge_dims(self.defaults, _dims)

        event = KPIEvent(
            **({"@timestamp": timestamp} if timestamp else {}),
            metric=Metric(name=name, type=type, unit=unit, value=value),
            dims=merged_dims,
            cost=(Cost(**cost) if cost else None),
            quantities=(Quantities(**quantities) if quantities else None),
            labels=list(labels or []),
            source=self.defaults.source,
            trace=(Trace(**trace) if trace else None),
        )
        self.store.index_event(event)

    # ---- simple helpers ------------------------------------------------------
    def count(
        self,
        name: str,
        inc: int = 1,
        *,
        dims: Optional[Dims] = None,
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ):
        """
        Counter helper for discrete occurrences (errors, doc views, retries).

        Intent:
        - Normalize all counters to unit="count" and float value, so sinks remain homogeneous.
        """
        self.emit(
            name=name,
            type="counter",
            value=float(inc),
            unit="count",
            dims=dims,
            labels=labels,
            actor=actor,
        )

    def gauge(
        self,
        name: str,
        value: float,
        *,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        actor: KPIActor,
    ):
        """
        Gauge helper for instantaneous values (queue size, memory, #chunks).

        Note:
        - Gauges represent snapshots; they aren't aggregated like counters.
        """
        self.emit(
            name=name,
            type="gauge",
            value=float(value),
            unit=unit,
            dims=dims,
            actor=actor,
        )

    # ---- timers: context & decorator ----------------------------------------
    class _TimerCtx:
        """
        Context manager timing helper.

        Why:
        - Guarantees emission even on exceptions.
        - Standardizes the 'status' dimension to "ok" or "error" automatically.
        """

        def __init__(
            self,
            svc: "KPIWriter",
            metric_name: str,
            dims: Optional[Dims],
            unit: str,
            labels: Optional[Iterable[str]],
            actor: KPIActor,
        ):
            self.svc = svc
            self.metric_name = metric_name
            self.unit = unit
            self.dims = dict(dims or {})
            self.actor = actor
            self.labels = labels
            self._t0 = 0.0

        def __enter__(self):
            self._t0 = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc, tb):
            dur_ms = (time.perf_counter() - self._t0) * 1000.0
            status = "error" if exc_type else (self.dims.get("status") or "ok")
            dims = dict(self.dims)
            dims["status"] = status
            self.svc.emit(
                name=self.metric_name,
                type="timer",
                value=dur_ms,
                unit=self.unit,
                dims=dims,
                actor=self.actor,
                labels=self.labels,
            )
            # do not swallow exceptions
            return False

    def timer(
        self,
        name: str,
        *,
        dims: Optional[Dims] = None,
        unit: str = "ms",
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> "_TimerCtx":
        """Timing context. Usage: `with kpi.timer('vectorization.duration_ms', actor=actor): ...`"""
        return KPIWriter._TimerCtx(self, name, dims, unit, labels, actor)

    def timed(
        self,
        name: str,
        *,
        unit: str = "ms",
        static_dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> Callable:
        """
        Timing decorator with fixed dims. Usage:

            @kpi.timed('agent.tool_latency_ms', static_dims={'agent_id':'fred','tool_name':'search'}, actor=actor)
            def call_tool(...): ...

        Why:
        - Makes it trivial to instrument hot paths without boilerplate.
        """

        def deco(fn: Callable):
            def wrapped(*args, **kwargs):
                with self.timer(name, unit=unit, dims=static_dims, actor=actor):
                    return fn(*args, **kwargs)

            return wrapped

        return deco

    # ---- opinionated domain helpers -----------------------------------------
    def log_llm(
        self,
        *,
        scope_type: Optional[str],  # "session" | "project" | "library"
        scope_id: Optional[str],  # the id within that scope
        exchange_id: Optional[str],
        agent_id: Optional[str],
        model: Optional[str],
        latency_ms: float,
        tokens_prompt: int,
        tokens_completion: int,
        usd: float,
        status: str = "ok",
        actor: KPIActor,
    ):
        """
        Record one LLM request: latency + tokens + cost, with scope and agent context.

        Design choices:
        - We emit as a 'timer' to naturally compose with latency dashboards.
        - Costs/tokens go into `cost` so finance views can pivot by scope/actor/model.
        - `scope_type/scope_id` allow the same code to serve conversation/project/library analytics.
        """
        dims = {
            "exchange_id": exchange_id,
            "agent_id": agent_id,
            "model": model,
            "status": status,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
        self.emit(
            name="llm.request_latency_ms",
            type="timer",
            value=latency_ms,
            unit="ms",
            dims=dims,
            cost={
                "tokens_prompt": tokens_prompt,
                "tokens_completion": tokens_completion,
                "tokens_total": tokens_prompt + tokens_completion,
                "usd": usd,
            },
            actor=actor,
        )

    def doc_used(
        self,
        *,
        agent_id: Optional[str],
        doc_uid: str,
        doc_source: Optional[str] = None,
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ):
        """
        Count a document usage event (retrieval/exposure to the user).

        Why:
        - This is a key adoption KPI for RAG experiences.
        - Dimensions keep it joinable with agent, scope, and doc source.
        """
        self.count(
            "doc.used_total",
            1,
            dims={
                "agent_id": agent_id,
                "doc_uid": doc_uid,
                "doc_source": doc_source,
                "scope_type": scope_type,
                "scope_id": scope_id,
            },
            actor=actor,
        )

    def vectorization_result(
        self,
        *,
        doc_uid: str,
        file_type: Optional[str],
        model: Optional[str],
        bytes_in: Optional[int],
        chunks: Optional[int],
        vectors: Optional[int],
        duration_ms: float,
        index: Optional[str],
        status: str = "ok",
        error_code: Optional[str] = None,
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ):
        """
        Emit vectorization metrics for a document ingestion step.

        Intent:
        - Single timer with quantities for bytes/chunks/vectors to correlate throughput.
        - Side counters/gauges offer quick totals without complex queries.
        - `status` + `error_code` normalize error taxonomy across ingestion pipelines.
        """
        self.emit(
            name="vectorization.duration_ms",
            type="timer",
            value=duration_ms,
            unit="ms",
            dims={
                "doc_uid": doc_uid,
                "file_type": file_type,
                "model": model,
                "index": index,
                "status": status,
                "error_code": error_code,
                "scope_type": scope_type,
                "scope_id": scope_id,
            },
            quantities={
                "bytes_in": bytes_in or 0,
                "chunks": chunks or 0,
                "vectors": vectors or 0,
            },
            actor=actor,
        )
        # Optional: also keep counters for totals/failures for simpler dashboards.
        if status == "error":
            self.count(
                "vectorization.failed_total",
                1,
                dims={"file_type": file_type, "model": model, "error_code": error_code},
                actor=actor,
            )
        if chunks is not None:
            self.gauge(
                "vectorization.chunks",
                float(chunks),
                dims={"file_type": file_type},
                actor=actor,
            )
        if vectors is not None:
            self.gauge(
                "vectorization.vectors",
                float(vectors),
                dims={"file_type": file_type},
                actor=actor,
            )

    # ---- API success/failure helpers (centralize error taxonomy) -------------
    def api_call(
        self,
        *,
        route: str,
        method: str,
        latency_ms: float,
        http_status: int,
        error_code: Optional[str] = None,
        exception_type: Optional[str] = None,
        extra_dims: Optional[Dims] = None,
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ):
        """
        Record an API call’s latency and outcome.

        Why here:
        - Ensures every endpoint reports with the same names and status logic.
        - Adds generic + API-specific error counters only on failures.
        - Supports enrichment via `extra_dims` (tool_name, model, index, …).
        """
        status = "ok" if 200 <= http_status < 400 else "error"
        dims = {
            "status": status,
            "http_status": str(http_status),
            "error_code": error_code,
            "exception_type": exception_type,
            "tool_name": None,  # left for symmetry; you can override via extra_dims
            "agent_step": None,
            "model": None,
            "index": None,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
        if extra_dims:
            dims.update(extra_dims)
        dims["route"] = route
        dims["method"] = method.upper()
        # timer for API latency
        self.emit(
            name="api.request_latency_ms",
            type="timer",
            value=latency_ms,
            unit="ms",
            dims=dims,
            actor=actor,
        )
        if status == "error":
            # specific + generic counters
            self.count("api.error_total", 1, dims=dims, actor=actor)
            self.count("error.total", 1, dims=dims, actor=actor)

    def api_error(
        self,
        *,
        route: str,
        method: str,
        http_status: int,
        error_code: str,
        exception_type: Optional[str] = None,
        extra_dims: Optional[Dims] = None,
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ):
        """
        Increment error counters directly when you don’t have a measured latency.

        Usage:
          kpi.api_error(route="/upload", method="POST", http_status=413, error_code="payload_too_large", ...)
        """
        dims = {
            "status": "error",
            "http_status": str(http_status),
            "error_code": error_code,
            "exception_type": exception_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
        if extra_dims:
            dims.update(extra_dims)
        dims["route"] = route
        dims["method"] = method.upper()
        self.count("api.error_total", 1, dims=dims, actor=actor)
        self.count("error.total", 1, dims=dims, actor=actor)

    def record_error(
        self,
        *,
        where: str,  # short label: 'vectorize.pdf', 'retrieval.search', 'jwt.decode'
        exception: BaseException,
        error_code: Optional[str] = None,
        extra_dims: Optional[Dims] = None,
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ):
        """
        Generic error counter from arbitrary code paths.

        Why:
        - Centralizes error taxonomy (status/error_code/exception_type) even outside API/LLM calls.
        - Keeps dashboards coherent when exceptions originate deep in tool or agent code.
        """
        dims = {
            "status": "error",
            "error_code": error_code,
            "exception_type": type(exception).__name__,
            "agent_step": where,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
        if extra_dims:
            dims.update(extra_dims)
        self.count("error.total", 1, dims=dims, actor=actor)
