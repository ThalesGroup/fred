"""Shared helpers to detect expired access tokens in HTTP responses/errors."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _is_expired_www_authenticate(header_val: Optional[str]) -> bool:
    if not header_val:
        return False
    hv = header_val.lower()
    return "token expired" in hv or ("expired" in hv and "token" in hv)


def _is_expired_body(body: Optional[str]) -> bool:
    if not body:
        return False
    b = body.lower()
    return (
        "token has expired" in b
        or "token expired" in b
        or ("expired" in b and "token" in b)
    )


def unwrap_httpx_status_error(exc: BaseException) -> httpx.HTTPStatusError | None:
    """Walks chained/ExceptionGroup errors to find an httpx.HTTPStatusError."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]  # type: ignore[assignment]

    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))

        if isinstance(cur, httpx.HTTPStatusError):
            return cur

        cause = getattr(cur, "__cause__", None)
        if cause:
            stack.append(cause)
        context = getattr(cur, "__context__", None)
        if context:
            stack.append(context)

        exceptions = getattr(cur, "exceptions", None)
        if isinstance(exceptions, tuple):
            stack.extend(exceptions)

    return None


def is_expired_httpx_status_error(err: httpx.HTTPStatusError) -> bool:
    """Detect a 401 specifically due to an expired token."""
    resp = getattr(err, "response", None)
    if not resp or resp.status_code != 401:
        return False
    try:
        if _is_expired_www_authenticate(resp.headers.get("www-authenticate")):
            return True
    except Exception:
        logger.warning(
            "[SECURITY][HTTP] Error checking www-authenticate header for token expiry",
            exc_info=True,
        )
        pass
    try:
        if _is_expired_body(resp.text):
            return True
    except Exception:
        logger.warning(
            "[SECURITY][HTTP] Error checking response body for token expiry",
            exc_info=True,
        )
        pass
    return False


def is_expired_httpx_response(resp: httpx.Response | None) -> bool:
    if not resp or resp.status_code != 401:
        return False
    try:
        if _is_expired_www_authenticate(resp.headers.get("www-authenticate")):
            return True
    except Exception:
        logger.warning(
            "[SECURITY][HTTP] Error checking www-authenticate header for token expiry",
            exc_info=True,
        )
        pass
    try:
        if _is_expired_body(resp.text):
            return True
    except Exception:
        logger.warning(
            "[SECURITY][HTTP] Error checking response body for token expiry",
            exc_info=True,
        )
        pass
    return False
