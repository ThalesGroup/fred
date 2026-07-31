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

"""PodApplicationContext — single composition root for a fred-runtime agent pod."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

import httpx
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_factory import build_kpi_writer
from fred_core.kpi.kpi_process import emit_process_kpis, emit_sql_pool_kpis
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_sdk.contracts.runtime import HistoryStorePort
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_runtime.app.config import AgentPodConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Dedicated to control-plane runtime-binding calls only (TURN-01) — a
# per-turn resolution, not the LLM/KF traffic shape, hence deliberately
# smaller pool bounds than fred_core.model.http_clients.
_CONTROL_PLANE_CLIENT_TIMEOUT = httpx.Timeout(10.0)
_CONTROL_PLANE_CLIENT_LIMITS = httpx.Limits(
    max_connections=50, max_keepalive_connections=20, keepalive_expiry=10.0
)

# Bounds the one-time connectivity check in initialize_sql() — asyncpg's own
# connect timeout defaults to 60s, which would otherwise let a single boot
# attempt hang well past what a readiness-driven operator expects.
_SQL_BOOT_PING_TIMEOUT_S = 5.0


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
    1. initialize_kpi_writer()          — sync, fast; needed by bootstrap_observability
    2. initialize_control_plane_client() — sync, fast; no network until first call
    3. initialize_sql()                 — async; may take time on first start
    4. start_metrics_exporter()         — sync; starts prometheus thread if configured
    5. start_kpi_tasks()                — async; starts background asyncio tasks
    """

    def __init__(self, configuration: AgentPodConfig) -> None:
        self.configuration = configuration
        self._sql_engine: AsyncEngine | None = None
        self._checkpointer: object | None = None
        self._history_store: HistoryStorePort | None = None
        self._kpi_writer: BaseKPIWriter | None = None
        self._control_plane_http_client: httpx.AsyncClient | None = None
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
        self._kpi_writer = build_kpi_writer(
            kpi_config=config.observability.kpi,
            opensearch_config=config.storage.opensearch,
            service_name="fred-runtime",
            log_level=config.app.log_level,
        )

    def initialize_control_plane_client(self) -> None:
        """Build the pod-wide async HTTP client for control-plane runtime-binding calls."""
        self._control_plane_http_client = httpx.AsyncClient(
            timeout=_CONTROL_PLANE_CLIENT_TIMEOUT,
            limits=_CONTROL_PLANE_CLIENT_LIMITS,
        )

    async def initialize_sql(self) -> None:
        """Build SQL engine, checkpointer, and history store.

        Durable storage is mandatory for every fred-runtime pod — dev uses a
        local SQLite file (`sqlite_path`), production uses Postgres, but both
        are "durable", never "no storage". Any failure here (bad config,
        unreachable/misconfigured Postgres) must abort pod startup so the
        FastAPI lifespan never completes and Kubernetes never routes traffic
        to this replica — see RUNTIME-EXECUTION-CONTRACT.md §8 (dated entry)
        for the incident this closes.
        """
        from fred_core.history.postgres_history_store import PostgresHistoryStore
        from fred_core.sql.base_sql import create_async_engine_from_config
        from fred_core.users.store.postgres_user_store import init_user_store
        from sqlalchemy import text

        from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer

        postgres_config = self.configuration.storage.postgres
        engine = create_async_engine_from_config(postgres_config)

        async def _ping() -> None:
            # SQLAlchemy async engines are lazy — nothing above opened a real
            # connection. Without this, an unreachable/misconfigured Postgres
            # would pass initialize_sql() silently and only fail mid-turn.
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        try:
            await asyncio.wait_for(_ping(), timeout=_SQL_BOOT_PING_TIMEOUT_S)
        except Exception as exc:
            logger.error(
                "[fred-runtime] SQL storage unreachable at startup — "
                "dialect=%s host=%s port=%s database=%s error_type=%s",
                engine.dialect.name,
                postgres_config.host,
                postgres_config.port,
                postgres_config.database,
                type(exc).__name__,
            )
            # This engine never reaches self._sql_engine on this path, so
            # shutdown()'s own dispose() (below) can never reach it either —
            # dispose it here or it leaks. Harmless today (the sole caller,
            # agent_app.py's lifespan, has no retry and the process exits on
            # this raise) but becomes a real leak the moment any retry/backoff
            # wrapper is added around initialize_sql() or the lifespan.
            await engine.dispose()
            raise

        init_user_store(engine)
        checkpointer = FredSqlCheckpointer(engine, kpi=self.get_kpi_writer())
        history_store = PostgresHistoryStore(engine, kpi=self.get_kpi_writer())
        self._sql_engine = engine
        self._checkpointer = checkpointer
        self._history_store = history_store
        logger.info(
            "[fred-runtime] SQL checkpointer and history store ready (dialect=%s)",
            engine.dialect.name,
        )

    def start_metrics_exporter(self) -> None:
        """Start the Prometheus scrape endpoint when configured."""
        prom_cfg = self.configuration.observability.kpi.prometheus
        if not prom_cfg.enabled:
            return
        result = start_http_server(prom_cfg.port, addr=prom_cfg.address)
        self._metrics_exporter = result if isinstance(result, tuple) else None
        logger.info(
            "[fred-runtime] Prometheus metrics exporter ready at %s:%s",
            prom_cfg.address,
            prom_cfg.port,
        )

    async def start_kpi_tasks(self) -> None:
        """Start background KPI flush tasks (process + SQL pool health)."""
        kpi_writer = self.get_kpi_writer()
        interval_s = float(
            self.configuration.observability.kpi.process_metrics_interval_sec
        )
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

    def get_control_plane_http_client(self) -> httpx.AsyncClient:
        if self._control_plane_http_client is None:
            raise RuntimeError(
                "Control-plane HTTP client not initialized — "
                "call initialize_control_plane_client() first"
            )
        return self._control_plane_http_client

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
        if self._control_plane_http_client is not None:
            await self._control_plane_http_client.aclose()
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
