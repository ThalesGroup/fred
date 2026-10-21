# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Authenticated one-shot API; backend control privileges stay in this process."""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult
from pydantic import ValidationError

from .backend import SandboxBackend
from .command import SubprocessRunner
from .config import BrokerSettings
from .docker_backend import DockerBackend
from .kubernetes_backend import KubernetesBackend
from .pool import WarmPool

logger = logging.getLogger(__name__)
_MAX_REQUEST_BYTES = 20_000


def create_app(
    settings: BrokerSettings | None = None, backend: SandboxBackend | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings or BrokerSettings.from_environment()
        selected_backend = backend or (
            DockerBackend(config, SubprocessRunner())
            if config.backend == "docker"
            else KubernetesBackend(config, SubprocessRunner())
        )
        pool = WarmPool(selected_backend, config)
        await pool.start()
        app.state.settings = config
        app.state.pool = pool
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def health() -> dict[str, int]:
        return {
            "ready": app.state.pool.ready_count,
            "allocated": app.state.pool.allocated_count,
            "limit": app.state.settings.max_sandboxes,
            "warm_target": app.state.settings.warm_pool_size,
            "cold_on_miss": int(app.state.settings.cold_start_on_miss),
        }

    @app.post("/v1/execute")
    async def execute(request: Request) -> JSONResponse:
        config: BrokerSettings = app.state.settings
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {config.token}"):
            return _error(401, "unauthorized")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > _MAX_REQUEST_BYTES:
                return _error(413, "invalid_request")
            body.extend(chunk)
        try:
            execution = SandboxRequest.model_validate_json(body)
        except ValidationError:
            return _error(400, "invalid_request")
        pool: WarmPool = app.state.pool
        try:
            lease = await pool.acquire()
        except SandboxError as exc:
            return _error(429 if exc.code == "busy" else 503, exc.code)
        except Exception:
            logger.exception("Sandbox preparation failed")
            return _error(503, "backend_failed")
        try:
            try:
                result = await asyncio.wait_for(
                    pool.backend.execute(lease, execution),
                    timeout=config.execution_timeout_seconds + 3,
                )
            except TimeoutError:
                result = SandboxResult(
                    exit_code=None, stdout="", stderr="", timed_out=True
                )
            return JSONResponse(result.model_dump())
        except SandboxError as exc:
            return _error(503, exc.code)
        except Exception:
            logger.exception("Sandbox execution failed")
            return _error(503, "backend_failed")
        finally:
            pool.schedule_release(lease)

    return app


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse({"error_code": code}, status_code=status_code)
