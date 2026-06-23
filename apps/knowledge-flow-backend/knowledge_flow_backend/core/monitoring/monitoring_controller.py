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


class MonitoringController:
    def __init__(self, app: APIRouter, application_context: Optional[ApplicationContext] = None):
        self._ctx = application_context

        @app.get("/healthz")
        async def healthz():
            return {"status": "ok"}

        @app.get("/ready")
        async def ready():
            checks = await self._run_checks()
            all_ok = all(c.get("ok", False) for c in checks.values()) if checks else True
            body = {"status": "ready" if all_ok else "degraded", "checks": checks}
            return JSONResponse(status_code=200 if all_ok else 503, content=body)

    async def _run_checks(self) -> dict:
        if self._ctx is None:
            return {}

        probes: dict[str, Callable[[], Awaitable[object | None]]] = {
            "postgres": self._check_postgres,
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
