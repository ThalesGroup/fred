# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""
Answer a `PlatformFailure` with the dependency that failed, never its text.

Why this lives in Knowledge Flow: it is the only service whose dependency
clients raise `PlatformFailure`. `create_app` registers it once, next to the
shared handlers of fred-core.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fred_core.common.platform_failure import MISCONFIGURED_STATUS, PlatformFailure

logger = logging.getLogger(__name__)

# Neutral on purpose: `failure` says which dependency; no host, bucket or value.
_PLATFORM_MISCONFIGURED_DETAIL = "A dependency refused this service's configuration."
_PLATFORM_UNAVAILABLE_DETAIL = "A dependency of this service is unavailable."


def register_platform_failure_handler(app: FastAPI) -> None:
    """Map a refused configuration to 502 and an unreachable dependency to 503."""

    @app.exception_handler(PlatformFailure)
    async def platform_failure_handler(request: Request, exc: PlatformFailure) -> JSONResponse:
        """Say which dependency failed and why; the log keeps its own text."""
        failure = exc.failure
        logger.error(
            "Platform dependency failure",
            exc_info=exc,
            extra={
                "failure_code": failure.code.value,
                "failure_origin": failure.origin.value if failure.origin else None,
                "failure_setting": failure.setting,
            },
        )
        return JSONResponse(
            status_code=exc.status,
            content={
                "detail": _PLATFORM_MISCONFIGURED_DETAIL if exc.status == MISCONFIGURED_STATUS else _PLATFORM_UNAVAILABLE_DETAIL,
                "failure": failure.model_dump(mode="json", include={"code", "origin", "setting"}),
            },
        )
