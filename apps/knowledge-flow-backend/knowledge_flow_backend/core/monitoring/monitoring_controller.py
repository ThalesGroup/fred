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

"""Liveness (`/healthz`) and dependency-aware readiness (`/ready`) endpoints.

`/healthz` stays a trivial liveness check (used by the k8s liveness/startup probes).
`/ready` actively probes each backend (Postgres, OpenSearch, OpenFGA, and the GCS
content store + virtual filesystem) with a per-check timeout, so an operator (or the
fredlab-status command) sees exactly *which* dependency is down instead of a silent
hang. Each probe is bounded by a timeout, so a stalled dependency reports as failed
rather than blocking the request.
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from knowledge_flow_backend.application_context import ApplicationContext

logger = logging.getLogger(__name__)

# Per-dependency probe budget. Kept under typical gateway timeouts so a stalled
# backend surfaces as a failed check, never as a hung request.
_READINESS_TIMEOUT_S = 6.0

# Probes that are REPORTED but never make the pod unready.
#
# Readiness answers one question: should the Service route traffic here? A dependency
# only some endpoints need must not answer "no" on behalf of all the others. The task
# database (OPS-04, issue #2170) backs `GET /tasks`, task SSE and ingestion *start* —
# document search, upload, tag and metadata reads never touch it. Failing readiness on
# it would pull every pod out of the Service after ~100s (failureThreshold 10 ×
# periodSeconds 10) and turn a partial outage into a total one.
#
# The signal is not lost: the failing check still appears in the body with ok=false and
# its error, still logs a warning, and is still what an operator or a status script
# reads. Only the HTTP status and the Kubernetes verdict are left alone.
_ADVISORY_PROBES = frozenset({"postgres_tasks"})

# Every probe — advisory or blocking — shares `_READINESS_TIMEOUT_S`.
#
# Deliberately NOT a shorter budget for advisory probes. The reasoning that tempts one:
# `_run_checks` gathers concurrently, so /ready's latency is the slowest probe, and kubelet
# abandons the request at its own `timeoutSeconds` and records a FAILED probe regardless of
# the 200 that would have come back — so an advisory probe that is slow takes the pod down
# via the very response that says "keep routing to me".
#
# That failure is real, but the fix belongs in the chart, not here: readinessProbe sets
# `timeoutSeconds: 8` (> this budget) so a slow advisory probe still answers in time and a
# blocking one can still spend its full budget before answering 503 honestly. Tightening the
# budget here instead would fire on load rather than on failure — `_check_postgres_tasks`
# does byte-identical work to `_check_postgres` but against a 2-connection pool with
# `pool_pre_ping`, so two concurrent task writes are enough to blow a short budget and emit
# `ready_degraded` plus a WARNING every `periodSeconds`, indistinguishable from a real outage.
#
# If you change `timeoutSeconds` in deploy/charts/fred/values.yaml, keep it above this.

# Server + database identity, for proving the task engine really is a second database.
# `system_identifier` identifies the *server cluster*; `inet_server_addr()` would not —
# it reports the address the client connected to, so the same server answers 127.0.0.1
# in-cluster and its routable IP from outside, and two spellings of one host would look
# like two servers. Both are readable by an ordinary (non-superuser) login role.
_PG_IDENTITY_SQL = text("SELECT (SELECT system_identifier FROM pg_control_system()) AS server_id, current_database() AS db")


class MonitoringController:
    def __init__(self, app: APIRouter, application_context: Optional[ApplicationContext] = None):
        self._ctx = application_context
        # None = not yet determined. Identity cannot change under a running process, so it
        # is resolved once and cached — a per-probe pair of extra connections against a
        # deliberately small pool would fire on load rather than on failure.
        self._task_db_is_distinct: Optional[bool] = None

        @app.get("/healthz")
        async def healthz():
            return {"status": "ok"}

        @app.get("/ready")
        async def ready():
            checks = await self._run_checks()
            # Only non-advisory failures make the pod unready — see _ADVISORY_PROBES.
            blocking_ok = all(c.get("ok", False) for name, c in checks.items() if name not in _ADVISORY_PROBES)
            advisory_failures = [name for name, c in checks.items() if name in _ADVISORY_PROBES and not c.get("ok", False)]

            if not blocking_ok:
                status = "degraded"
            elif advisory_failures:
                # Serving, but a non-essential dependency is down. Distinct from "ready"
                # so a dashboard or status script can tell the two apart at a glance.
                status = "ready_degraded"
            else:
                status = "ready"

            body: dict = {"status": status, "checks": checks}
            if advisory_failures:
                body["advisory_failures"] = advisory_failures
            return JSONResponse(status_code=200 if blocking_ok else 503, content=body)

    async def _run_checks(self) -> dict:
        if self._ctx is None:
            return {}

        probes: dict[str, Callable[[], Awaitable[object | None]]] = {
            "postgres": self._check_postgres,
            "postgres_tasks": self._check_postgres_tasks,
            "opensearch": self._check_opensearch,
            "openfga": self._check_openfga,
            "gcs_filesystem": self._check_gcs_filesystem,
            "gcs_content_store": self._check_gcs_content_store,
        }
        results: dict[str, dict] = {}

        async def run_one(name: str, fn: Callable[[], Awaitable[object | None]]) -> None:
            started = time.monotonic()
            try:
                detail = await asyncio.wait_for(fn(), timeout=_READINESS_TIMEOUT_S)
                entry = {"ok": True, "elapsed_ms": int((time.monotonic() - started) * 1000)}
                if isinstance(detail, dict):
                    entry.update(detail)
                results[name] = entry
            except _SkippedCheck as skip:
                results[name] = {"ok": True, "skipped": str(skip)}
            except Exception as exc:  # noqa: BLE001 — report any failure as a down dependency
                results[name] = {
                    "ok": False,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                }
                logger.warning("[READY] dependency '%s' check failed: %s", name, exc)

        await asyncio.gather(*(run_one(name, fn) for name, fn in probes.items()))
        return results

    # --- individual probes (raise on failure, return optional detail dict) ---

    @property
    def _context(self) -> ApplicationContext:
        # Probes only run after _run_checks() confirms the context is set.
        if self._ctx is None:
            raise RuntimeError("ApplicationContext is required for readiness probes")
        return self._ctx

    async def _check_postgres(self) -> None:
        engine = self._context.get_pg_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def _check_postgres_tasks(self) -> None:
        """Probe the dedicated task database (OPS-04, issue #2170).

        Without this, a pod whose task database is down — or whose
        POSTGRES_KNOWLEDGE_FLOW_PASSWORD was rotated — reports nothing at all about it,
        while every `GET /tasks`, task SSE stream and ingestion start returns 500 and the
        shared engine that used to be the only thing checked stays perfectly healthy.

        ADVISORY (see `_ADVISORY_PROBES`): a failure here is reported in the body and
        logged, but does NOT make the pod unready. Document search, upload, tag and
        metadata reads do not touch this database, and taking every pod out of the
        Service would convert a partial outage into a total one.

        Skipped rather than duplicated when `storage.task_postgres` is unset: the task
        engine is then the shared engine, which `_check_postgres` already covers.

        Also the only check that can prove the two engines address *different* databases.
        `StorageConfig._task_postgres_must_be_a_different_database` compares how the blocks
        are spelled, so `localhost` and `127.0.0.1` pass it; only asking both servers who
        they are settles it, and getting it wrong silently restores the duplicate rows this
        whole change removes.
        """
        ctx = self._context
        if ctx.get_config().storage.task_postgres is None:
            raise _SkippedCheck("task_postgres not configured; shares the main postgres engine")
        engine = ctx.get_task_pg_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            if self._task_db_is_distinct is None and conn.dialect.name == "postgresql":
                task_identity = (await conn.execute(_PG_IDENTITY_SQL)).one()
                async with ctx.get_pg_async_engine().connect() as shared_conn:
                    shared_identity = (await shared_conn.execute(_PG_IDENTITY_SQL)).one()
                self._task_db_is_distinct = tuple(task_identity) != tuple(shared_identity)
        if self._task_db_is_distinct is False:
            raise RuntimeError(
                "storage.task_postgres resolves to the SAME database as storage.postgres "
                "(same server system_identifier and current_database), however differently the two "
                "blocks are spelled. Control-plane and Knowledge Flow are reading each other's task "
                "rows and the Activity page shows every task twice (OPS-04, issue #2170)."
            )

    async def _check_opensearch(self) -> None:
        try:
            client = self._context.get_opensearch_client()
        except Exception as exc:  # noqa: BLE001
            raise _SkippedCheck(f"opensearch not configured ({exc})") from exc
        ok = await asyncio.to_thread(client.ping)
        if not ok:
            raise RuntimeError("OpenSearch ping returned False")

    async def _check_openfga(self) -> None:
        from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine

        engine = self._context.get_rebac_engine()
        if not isinstance(engine, OpenFgaRebacEngine):
            raise _SkippedCheck(f"rebac not OpenFGA-backed ({type(engine).__name__})")
        # get_client() resolves the store + syncs the model on first call, then caches.
        # Bounded by the OpenFGA client timeout, so a stalled engine fails fast here.
        await engine.get_client()

    async def _check_gcs_filesystem(self) -> object:
        return await self._check_backend_health(self._context.get_filesystem(), "filesystem")

    async def _check_gcs_content_store(self) -> object:
        return await self._check_backend_health(self._context.get_content_store(), "content store")

    @staticmethod
    async def _check_backend_health(backend: object, label: str) -> object:
        health_check = getattr(backend, "health_check", None)
        if health_check is None:
            raise _SkippedCheck(f"{type(backend).__name__} has no health_check (non-GCS {label})")
        return await asyncio.to_thread(health_check)


class _SkippedCheck(Exception):
    """Raised by a probe when the dependency is not applicable for this config."""
