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

from fred_core import KeycloakUser
from fred_core.logs.context import current_context, request_log_scope
from fred_core.logs.propagation import bind_received_log_context, encode_log_context
from fred_core.security.structure import is_service_agent
from temporalio import activity

from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")
_STAGE_FIELDS = {"document_uid", "task_id", "attachment_id", "tool_name", "workflow_id", "workflow_run_id", "activity_id", "activity_attempt"}


def capture_ingestion_context(user: KeycloakUser, definition: PipelineDefinition, team_ids: dict[str, str | None]) -> None:
    """Capture before the immutable outbox transaction, never from later delivery."""
    values = {key: value for key, value in current_context().items() if key not in _STAGE_FIELDS and key != "team_id"}
    values["correlation_id"] = values.get("correlation_id") or str(uuid4())
    values["workflow_id"] = definition.workflow_id
    if not is_service_agent(user):
        values["user_id"] = user.uid
    else:
        values.pop("user_id", None)
    teams = set(team_ids.values())
    if len(teams) == 1 and None not in teams:
        values["team_id"] = next(iter(teams))
    encoded = encode_log_context(values)
    if encoded is None:
        logger.warning("Ingestion logging metadata reduced", extra={"reason": "invalid_context"})
        encoded = encode_log_context({key: value for key, value in values.items() if key in {"correlation_id", "workflow_id", "user_id", "team_id"}})
    definition.logging_context = encoded
    for file in definition.files:
        file.logging_context = encoded


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
        task_id = bound.get("task_id") or getattr(file, "task_id", None)
        document_uid = getattr(metadata, "document_uid", None) or getattr(file, "document_uid", None)
        local: dict[str, object] = {}
        if user is not None and not is_service_agent(user):
            local["user_id"] = user.uid
        if task_id:
            local["task_id"] = task_id
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
            # Legacy queued jobs have no envelope. Derive a stable retry reference
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
