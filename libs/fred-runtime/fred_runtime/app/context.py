"""PodApplicationContext — single composition root for a fred-runtime agent pod."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_process import emit_process_kpis, emit_sql_pool_kpis
from fred_core.kpi.kpi_writer import KPIDefaults, KPIWriter
from fred_core.kpi.log_kpi_store import KpiLogStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore
from fred_sdk.contracts.runtime import HistoryStorePort
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_runtime.app.config import AgentPodConfig, MetricsBackend

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDicts for ring buffer entries
# ---------------------------------------------------------------------------


class _KpiTurnRequired(TypedDict):
    ts: str
    exchange_id: str
    session_id: str | None
    user_id: str
    total_ms: int
    is_error: bool


class KpiTurnRecord(_KpiTurnRequired, total=False):
    team_id: str | None
    template_agent_id: str | None
    runtime_id: str | None
    model_name: str | None
    finish_reason: str
    tool_count: int
    input_tokens: int | None
    output_tokens: int | None


class _AuditEventRequired(TypedDict):
    ts: str
    audit_event: str


class AuditEventRecord(_AuditEventRequired, total=False):
    user_id: str
    team_id: str | None
    agent_id: str | None
    agent_instance_id: str | None


# ---------------------------------------------------------------------------
# PodApplicationContext
# ---------------------------------------------------------------------------


class PodApplicationContext:
    """
    Single composition root for one fred-runtime pod.

    All resource construction is lazy and side-effect-free in __init__.
    Call the initialize_* methods inside the FastAPI lifespan after log setup.

    Boot order (enforced by lifespan):
    1. initialize_kpi_writer()   — sync, fast; needed by bootstrap_observability
    2. initialize_sql()          — async; may take time on first start
    3. start_metrics_exporter()  — sync; starts prometheus thread if configured
    4. start_kpi_tasks()         — async; starts background asyncio tasks
    """

    def __init__(self, configuration: AgentPodConfig) -> None:
        self.configuration = configuration
        self._sql_engine: AsyncEngine | None = None
        self._checkpointer: object | None = None
        self._history_store: HistoryStorePort | None = None
        self._kpi_writer: BaseKPIWriter | None = None
        self._metrics_exporter: tuple[object, ...] | None = None
        self._kpi_tasks: list[asyncio.Task[None]] = []
        self._kpi_turns_lock = threading.Lock()
        self._audit_events_lock = threading.Lock()
        self.kpi_turns_buffer: deque[KpiTurnRecord] = deque(maxlen=200)
        self.audit_events_buffer: deque[AuditEventRecord] = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Initialization steps — called in order from the FastAPI lifespan
    # ------------------------------------------------------------------

    def initialize_kpi_writer(self) -> None:
        """Build the KPI writer from pod observability config."""
        config = self.configuration
        backend = config.observability.metrics
        if backend == MetricsBackend.null:
            self._kpi_writer = NoOpKPIWriter()
            return
        store = KpiLogStore(level=config.app.log_level)
        if backend == MetricsBackend.prometheus:
            store = PrometheusKPIStore(delegate=store)  # type: ignore[arg-type]
        self._kpi_writer = KPIWriter(
            store=store,
            defaults=KPIDefaults(static_dims={"service": "fred-runtime"}),
            summary_interval_s=config.app.kpi_log_summary_interval_sec,
            summary_top_n=config.app.kpi_log_summary_top_n,
        )

    async def initialize_sql(self) -> None:
        """Build SQL engine, checkpointer, and history store (SQL-backed only)."""
        from fred_core.history.postgres_history_store import PostgresHistoryStore
        from fred_core.sql.base_sql import create_async_engine_from_config
        from fred_core.users.store.postgres_user_store import init_user_store

        from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer

        try:
            engine = create_async_engine_from_config(
                self.configuration.storage.postgres
            )
            init_user_store(engine)
            checkpointer = FredSqlCheckpointer(engine)
            history_store = PostgresHistoryStore(engine)
            self._sql_engine = engine
            self._checkpointer = checkpointer
            self._history_store = history_store
            logger.info(
                "[fred-runtime] SQL checkpointer and history store ready (dialect=%s)",
                engine.dialect.name,
            )
        except Exception:
            logger.exception(
                "[fred-runtime] Failed to initialize SQL storage — running stateless"
            )

    def start_metrics_exporter(self) -> None:
        """Start the Prometheus scrape endpoint when configured."""
        config = self.configuration
        if config.observability.metrics != MetricsBackend.prometheus:
            return
        result = start_http_server(
            config.app.metrics_port,
            addr=config.app.metrics_address,
        )
        self._metrics_exporter = result if isinstance(result, tuple) else None
        logger.info(
            "[fred-runtime] Prometheus metrics exporter ready at %s:%s",
            config.app.metrics_address,
            config.app.metrics_port,
        )

    async def start_kpi_tasks(self) -> None:
        """Start background KPI flush tasks (process + SQL pool health)."""
        kpi_writer = self.get_kpi_writer()
        config = self.configuration
        interval_s = float(config.app.kpi_process_metrics_interval_sec)
        if interval_s <= 0 or isinstance(kpi_writer, NoOpKPIWriter):
            return
        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(emit_process_kpis(interval_s, kpi_writer))
        ]
        if self._sql_engine is not None:
            tasks.append(
                asyncio.create_task(
                    emit_sql_pool_kpis(
                        interval_s,
                        kpi_writer,
                        self._sql_engine,
                        pool_name="fred-runtime-postgres",
                    )
                )
            )
        self._kpi_tasks = tasks

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_sql_engine(self) -> AsyncEngine | None:
        return self._sql_engine

    def get_checkpointer(self) -> object | None:
        return self._checkpointer

    def get_history_store(self) -> HistoryStorePort | None:
        return self._history_store

    def get_kpi_writer(self) -> BaseKPIWriter:
        if self._kpi_writer is None:
            raise RuntimeError(
                "KPI writer not initialized — call initialize_kpi_writer() first"
            )
        return self._kpi_writer

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Cancel background tasks, dispose SQL engine, stop metrics exporter."""
        for task in self._kpi_tasks:
            task.cancel()
        if self._kpi_tasks:
            await asyncio.gather(*self._kpi_tasks, return_exceptions=True)
        self._kpi_tasks = []
        if self._sql_engine is not None:
            await self._sql_engine.dispose()
            logger.info("[fred-runtime] SQL engine disposed")
        self._stop_metrics_exporter()

    def _stop_metrics_exporter(self) -> None:
        if self._metrics_exporter is None:
            return
        exporter = self._metrics_exporter
        server = exporter[0] if isinstance(exporter, tuple) and exporter else exporter
        shutdown = getattr(server, "shutdown", None)
        if callable(shutdown):
            shutdown()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
