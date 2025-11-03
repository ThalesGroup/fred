# noop_kpi_writer.py
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Callable, ContextManager, Iterable, Optional

from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

from .base_kpi_writer import BaseKPIWriter


class NoOpKPIWriter(BaseKPIWriter):
    """
    Why this exists in Fred:
    - Unit/integration tests shouldn’t depend on metric sinks.
    - Local dev can keep code instrumented without requiring infra.
    - Contract stays identical; emissions are simply discarded.
    """

    # ---- core primitive ------------------------------------------------------
    def emit(
        self,
        *,
        name: str,
        type: str,
        value: Optional[float] = None,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        cost: Optional[dict] = None,
        quantities: Optional[dict] = None,
        labels: Optional[Iterable[str]] = None,
        trace: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
        actor: KPIActor,
    ) -> None:
        return  # no-op

    # ---- simple helpers ------------------------------------------------------
    def count(
        self,
        name: str,
        inc: int = 1,
        *,
        dims: Optional[Dims] = None,
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> None:
        return

    def gauge(
        self,
        name: str,
        value: float,
        *,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> None:
        return

    # ---- timers --------------------------------------------------------------

    class _NoOpTimerImpl(AbstractContextManager):
        # FIX 1: Add __init__ to accept and store the initial dims.
        # Although not used, it prepares the class for yielding the dict.
        def __init__(self, dims: Optional[Dims]):
            # We must yield a mutable dictionary to satisfy the ContextManager[Dims] contract
            self.dims = dims.copy() if dims is not None else {}

        def __enter__(self) -> Dims:  # <--- CRITICAL FIX 2: Must return Dims
            # We yield the dictionary so that the user's code can execute:
            # `with kpi.timer(...) as d:` and then mutate `d` without error.
            return self.dims

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False  # Don't swallow exceptions

    def timer(
        self,
        name: str,
        *,
        dims: Optional[Dims] = None,
        unit: str = "ms",
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> ContextManager[Dims]:  # <--- CRITICAL FIX 3: Must return ContextManager[Dims]
        # FIX 4: Instantiate with initial dims
        return NoOpKPIWriter._NoOpTimerImpl(dims)

    def timed(
        self,
        name: str,
        *,
        unit: str = "ms",
        static_dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> Callable:
        def deco(fn: Callable):
            def wrapped(*args, **kwargs):
                # We must call self.timer to get the context manager,
                # even if it's a no-op, to ensure the context logic runs (for exceptions).
                with self.timer(name, unit=unit, dims=static_dims, actor=actor):
                    return fn(*args, **kwargs)

            return wrapped

        return deco

    # ---- domain helpers ------------------------------------------------------
    def log_llm(self, **kwargs) -> None:
        return

    def doc_used(self, **kwargs) -> None:
        return

    def vectorization_result(self, **kwargs) -> None:
        return

    def api_call(self, **kwargs) -> None:
        return

    def api_error(self, **kwargs) -> None:
        return

    def record_error(self, **kwargs) -> None:
        return
