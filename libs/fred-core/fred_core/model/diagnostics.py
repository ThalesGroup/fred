# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Content-free HTTP metadata for the active model call; never shared across calls."""

from __future__ import annotations

import logging
import math
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

import httpx

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


@dataclass
class ModelHttpObservation:
    started: float = field(default_factory=time.monotonic)
    allow_request_ids: bool = False
    fields: dict[str, str | int | float | bool] = field(default_factory=dict)


active_model_http: ContextVar[ModelHttpObservation | None] = ContextVar(
    "active_model_http", default=None
)


def observe_model_response(response: httpx.Response) -> None:
    """HTTPX calls this after headers, before consuming the streaming body."""
    observation = active_model_http.get()
    if observation is None:
        return
    observation.fields.clear()
    observation.fields.update(
        http_status=response.status_code,
        response_headers_ms=(time.monotonic() - observation.started) * 1000,
    )
    if (
        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "text/event-stream"
    ):
        observation.fields["response_streaming"] = True
    if observation.allow_request_ids:
        for header in ("x-request-id", "apim-request-id"):
            value = response.headers.get(header, "")
            if _REQUEST_ID.fullmatch(value):
                observation.fields[header.replace("-", "_")] = value


async def observe_async_model_response(response: httpx.Response) -> None:
    observe_model_response(response)


def effective_model_settings(
    model: object,
) -> dict[str, str | int | float | bool | None]:
    """Read only scalar settings from the constructed wrapper, never model dumps."""
    fields: dict[str, str | int | float | bool | None] = {}
    for key in ("streaming", "stream_chunk_timeout", "max_retries"):
        value = getattr(model, key, None)
        if value is None or isinstance(value, bool):
            fields[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(value):
            fields[key] = value
    disabled = getattr(model, "disable_streaming", None)
    if isinstance(disabled, bool) or disabled == "tool_calling":
        fields["disable_streaming"] = disabled
    root_client = getattr(model, "root_async_client", None)
    timeout = getattr(root_client, "timeout", getattr(model, "request_timeout", None))
    if timeout is None and root_client is not None:
        timeout = httpx.Timeout(None)
    if isinstance(timeout, (int, float, tuple)):
        timeout = httpx.Timeout(timeout)
    if isinstance(timeout, httpx.Timeout):
        for phase in ("connect", "read", "write", "pool"):
            value = getattr(timeout, phase)
            if value is None or (
                isinstance(value, (int, float)) and math.isfinite(value)
            ):
                fields[f"timeout_{phase}_s"] = value
    return fields


@lru_cache(maxsize=128)
def log_model_settings(
    provider: str, model_name: str, settings: tuple[tuple[str, object], ...]
) -> None:
    logger.info(
        "event=llm_model_configuration provider=%s model=%s settings=%s",
        provider,
        model_name,
        dict(settings),
    )
    _log_versions()


@lru_cache(maxsize=1)
def _log_versions() -> None:
    versions: dict[str, str] = {}
    for package in (
        "langchain-openai",
        "langchain-core",
        "deepagents",
        "openai",
        "httpx",
    ):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    logger.info("event=llm_client_versions versions=%s", versions)
