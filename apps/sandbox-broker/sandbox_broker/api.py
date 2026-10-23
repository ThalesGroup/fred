# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Authenticated one-shot API; backend control privileges stay in this process."""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult
from pydantic import ValidationError

from .agent_sandbox_backend import AgentSandboxBackend
from .backend import SandboxBackend
from .command import SubprocessRunner
from .config import BrokerSettings
from .docker_backend import DockerBackend
from .kubernetes_backend import KubernetesBackend
from .pool import OnDemandCapacity
from .sessions import ConversationPool
from .settings_sync import SettingsSync

logger = logging.getLogger(__name__)
_MAX_REQUEST_BYTES = 20_000


def create_app(
    settings: BrokerSettings | None = None, backend: SandboxBackend | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings or BrokerSettings.from_environment()
        if backend is not None:
            selected_backend = backend
        elif config.backend == "docker":
            selected_backend = DockerBackend(config, SubprocessRunner())
        elif config.backend == "agent_sandbox":
            selected_backend = AgentSandboxBackend(config, SubprocessRunner())
        else:
            selected_backend = KubernetesBackend(config, SubprocessRunner())
        pool = OnDemandCapacity(selected_backend, config)
        await pool.start()
        sessions = ConversationPool(
            pool,
            idle_seconds=config.idle_timeout_seconds,
            max_sessions=config.max_sandboxes,
        )
        sessions.start()
        sync = SettingsSync(config, sessions)
        sync.start()
        app.state.settings = config
        app.state.pool = pool
        app.state.sessions = sessions
        app.state.settings_sync = sync
        try:
            yield
        finally:
            await sync.close()
            await sessions.close()
            await pool.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def health() -> dict[str, int]:
        return {
            "allocated": app.state.pool.allocated_count,
            "limit": app.state.settings.max_sandboxes,
            "active_conversations": app.state.sessions.active_count,
            "idle_timeout_seconds": app.state.sessions.idle_seconds,
        }

    @app.post("/v1/view-key")
    async def view_key(request: Request) -> JSONResponse:
        config: BrokerSettings = app.state.settings
        if not hmac.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {config.token}"
        ):
            return _error(401, "unauthorized")
        session_key = request.headers.get("X-Fred-Sandbox-Session", "")
        if not re.fullmatch(r"[a-f0-9]{64}", session_key):
            return _error(400, "invalid_request")
        try:
            return JSONResponse(
                {"view_key": await app.state.sessions.view_key(session_key)}
            )
        except SandboxError as exc:
            return _error(429 if exc.code == "busy" else 503, exc.code)

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
        session_key = request.headers.get("X-Fred-Sandbox-Session")
        if session_key is not None:
            if not re.fullmatch(r"[a-f0-9]{64}", session_key):
                return _error(400, "invalid_request")
            try:
                result = await app.state.sessions.execute(session_key, execution)
                return JSONResponse(result.model_dump())
            except SandboxError as exc:
                return _error(429 if exc.code == "busy" else 503, exc.code)
            except TimeoutError:
                return JSONResponse(
                    SandboxResult(
                        exit_code=None, stdout="", stderr="", timed_out=True
                    ).model_dump()
                )
            except Exception:
                logger.exception("Conversation sandbox execution failed")
                return _error(503, "backend_failed")
        pool: OnDemandCapacity = app.state.pool
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
