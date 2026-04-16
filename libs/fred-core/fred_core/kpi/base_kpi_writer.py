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

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, ContextManager, Iterable, Optional

from fred_core.kpi.kpi_writer_structures import Dims, KPIActor, MetricType


class BaseKPIWriter(ABC):
    """
    - This is the stable *emission* interface used by the app code.
    - Concrete implementations (e.g., OpenSearch/OTel-backed) plug behind it.
    - Tests can swap a NoOp or in-memory impl without touching callsites.
    """

    # ---- core primitive ------------------------------------------------------
    @abstractmethod
    def emit(
        self,
        *,
        name: str,
        type: MetricType,
        value: Optional[float] = None,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        cost: Optional[dict] = None,
        quantities: Optional[dict] = None,
        labels: Optional[Iterable[str]] = None,
        trace: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
        actor: KPIActor,
    ) -> None: ...

    @abstractmethod
    def timer(
        self,
        name: str,  # e.g. "api.request_latency_ms"
        *,
        dims: Optional[
            Dims
        ] = None,  # initial dims; you can add/override in the context
        unit: str = "ms",  # "ms" or "s" (match the metric name suffix)
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> ContextManager[Dims]:
        """
        Context manager that measures duration and emits once on exit.

        Usage:
            with kpi.timer("api.request_latency_ms",
                           dims={"route": "/upload", "method": "POST"},
                           actor=actor) as d:
                ... work ...
                d["status"] = "ok"  # or "error"/"timeout"
        Semantics:
            - On exception → emits with status="error" automatically.
            - Otherwise → uses d.get("status","ok").
        """

    @abstractmethod
    def timed(
        self,
        name: str,  # e.g. "agent.tool_latency_ms"
        *,
        unit: str = "ms",
        static_dims: Optional[Dims] = None,  # fixed dims baked into the decorator
        actor: KPIActor,
    ) -> Callable:
        """
        Decorator version of `timer()` for quick instrumentation.

        @kpi.timed("agent.tool_latency_ms", static_dims={"tool":"search"}, actor=actor)
        def call_tool(...): ...
        """

    # ---- simple helpers ------------------------------------------------------
    @abstractmethod
    def count(
        self,
        name: str,
        inc: int = 1,
        *,
        dims: Optional[Dims] = None,
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> None: ...

    @abstractmethod
    def gauge(
        self,
        name: str,
        value: float,
        *,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> None: ...

    # ---- domain helpers ------------------------------------------------------
    @abstractmethod
    def log_llm(
        self,
        *,
        scope_type: Optional[str],
        scope_id: Optional[str],
        exchange_id: Optional[str],
        agent_id: Optional[str],
        model: Optional[str],
        latency_ms: float,
        tokens_prompt: int,
        tokens_completion: int,
        usd: float,
        status: str,
        actor: KPIActor,
    ) -> None: ...

    @abstractmethod
    def doc_used(
        self,
        *,
        agent_id: Optional[str],
        doc_uid: str,
        doc_source: Optional[str],
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> None: ...

    @abstractmethod
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
        status: str,
        error_code: Optional[str],
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> None: ...

    @abstractmethod
    def api_call(
        self,
        *,
        route: str,
        method: str,
        latency_ms: float,
        http_status: int,
        error_code: Optional[str],
        exception_type: Optional[str],
        extra_dims: Optional[Dims],
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> None: ...

    @abstractmethod
    def api_error(
        self,
        *,
        route: str,
        method: str,
        http_status: int,
        error_code: str,
        exception_type: Optional[str],
        extra_dims: Optional[Dims],
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> None: ...

    @abstractmethod
    def record_error(
        self,
        *,
        where: str,
        exception: BaseException,
        error_code: Optional[str],
        extra_dims: Optional[Dims],
        actor: KPIActor,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> None: ...
