# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for details.

"""Diagnostic ownership at existing trusted ingestion submission/activity seams."""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar
from uuid import NAMESPACE_URL, uuid4, uuid5

from fred_core.logs.context import request_log_scope
from fred_core.logs.propagation import bind_received_log_context
from fred_core.security.structure import is_service_agent
from temporalio import activity

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")


def ingestion_activity(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Scope the existing activity and its actual thread work; preserve its signature."""
    signature = inspect.signature(func)

    @wraps(func)
    async def run(*args: P.args, **kwargs: P.kwargs) -> T:
        # This is a framework adapter: inspect supplies the original typed args.
        bound = signature.bind(*args, **kwargs).arguments
        file = bound.get("file")
        metadata = bound.get("metadata")
        user = bound.get("user") or getattr(file, "processed_by", None)
        header = bound.get("logging_context") or getattr(file, "logging_context", None)
        document_uid = getattr(metadata, "document_uid", None) or getattr(file, "document_uid", None)
        local: dict[str, object] = {}
        if user is not None and not is_service_agent(user):
            local["user_id"] = user.uid
        if document_uid:
            local["document_uid"] = document_uid
        if activity.in_activity():
            info = activity.info()
            local.update(
                {
                    key: value
                    for key, value in {
                        "workflow_id": info.workflow_id,
                        "workflow_run_id": info.workflow_run_id,
                        "activity_id": info.activity_id,
                        "activity_attempt": info.attempt,
                    }.items()
                    if value is not None
                }
            )
            # Derive a stable retry reference for diagnostics
            # outside workflow code; no random generation/import enters replay.
            correlation = str(uuid5(NAMESPACE_URL, info.workflow_id or info.activity_id))
        else:
            correlation = str(uuid4())
        started = asyncio.get_running_loop().time()
        outcome = "failed"
        with request_log_scope(correlation_id=correlation):
            bind_received_log_context(header, **local)
            try:
                result = await func(*args, **kwargs)
                outcome = "succeeded"
                return result
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                logger.info(
                    "Ingestion activity completed",
                    extra={
                        "outcome": outcome,
                        "duration_ms": (asyncio.get_running_loop().time() - started) * 1000,
                    },
                )

    return run
