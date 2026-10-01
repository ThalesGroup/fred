# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for details.

"""Request references and truthful completion for ordinary and streaming HTTP."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fred_core.logs.context import completion_log_scope, request_log_scope

logger = logging.getLogger("http")
REFERENCE_HEADERS = ["X-Request-ID", "X-Correlation-ID"]


@dataclass
class _ResponseState:
    status: int | None = None
    completed: bool = False
    disconnected: bool = False


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        response = _ResponseState()
        outcome = "failed"
        with request_log_scope(
            request_id=str(uuid4()), correlation_id=str(uuid4())
        ) as owner:

            async def request_receive() -> Message:
                message = await receive()
                if message["type"] == "http.disconnect":
                    response.disconnected = True
                return message

            async def response_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers["X-Request-ID"] = str(owner.values["request_id"])
                    headers["X-Correlation-ID"] = str(owner.values["correlation_id"])
                try:
                    await send(message)
                except OSError:
                    response.disconnected = True
                    raise
                if message["type"] == "http.response.start":
                    response.status = message["status"]
                elif message["type"] == "http.response.body" and not message.get(
                    "more_body", False
                ):
                    response.completed = True

            try:
                await self.app(scope, request_receive, response_send)
                outcome = (
                    "responded"
                    if response.completed
                    else "disconnected"
                    if response.disconnected
                    else "incomplete"
                )
            except asyncio.CancelledError:
                outcome = "disconnected" if response.disconnected else "cancelled"
                raise
            except ClientDisconnect:
                outcome = "disconnected"
                raise
            except OSError:
                outcome = "disconnected" if response.disconnected else "failed"
                raise
            finally:
                successful = (
                    response.completed
                    and outcome == "responded"
                    and response.status is not None
                    and response.status < 400
                )
                if not (
                    successful
                    and scope.get("path", "").endswith(("/healthz", "/ready"))
                ):
                    facts: dict[str, object] = {
                        "http_method": scope["method"],
                        "duration_ms": (time.perf_counter() - started) * 1000,
                        "outcome": outcome,
                    }
                    route = getattr(scope.get("route"), "path", None)
                    if isinstance(route, str) and len(route) <= 1024:
                        facts["route"] = route
                    if response.status is not None:
                        facts["http_status"] = response.status
                    level = (
                        logging.INFO
                        if successful
                        else logging.ERROR
                        if outcome == "failed"
                        or (response.status is not None and response.status >= 500)
                        else logging.WARNING
                    )
                    with completion_log_scope(owner.values):
                        logger.log(level, "HTTP request completed", extra=facts)
