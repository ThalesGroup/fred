# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

"""MCP tool call interceptors (retry, auth refresh, etc.)."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

import httpx
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from agentic_backend.common.token_expiry import (
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)

logger = logging.getLogger(__name__)


class ExpiredTokenRetryInterceptor:
    """
    Intercepts MCP tool calls; on expired-token 401 it refreshes the token and retries once.

    - Uses agent-provided `refresh_user_access_token` callback (sync) to fetch a new token.
    - Injects the fresh Authorization header on retry only (does not mutate base connection).
    """

    def __init__(self, refresh_token_cb: Callable[[], str]):
        self._refresh = refresh_token_cb

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable],
    ):
        try:
            return await handler(request)
        except Exception as e:  # noqa: BLE001
            http_err: httpx.HTTPStatusError | None = unwrap_httpx_status_error(e)
            if not http_err or not is_expired_httpx_status_error(http_err):
                raise

            logger.warning(
                "[MCP][%s] 401 expired token detected for tool=%s. Refreshing and retrying once.",
                request.server_name,
                request.name,
            )

            try:
                new_token = self._refresh()
            except Exception as refresh_err:  # noqa: BLE001
                logger.error(
                    "[MCP][%s] Token refresh failed; not retrying: %s",
                    request.server_name,
                    refresh_err,
                )
                raise

            if not new_token:
                logger.error(
                    "[MCP][%s] Token refresh returned empty token; aborting retry.",
                    request.server_name,
                )
                raise

            new_headers = dict(request.headers or {})
            new_headers["Authorization"] = f"Bearer {new_token}"
            retry_req = request.override(headers=new_headers)

            try:
                return await handler(retry_req)
            except Exception as e2:  # noqa: BLE001
                logger.error(
                    "[MCP][%s] Retry after refresh failed for tool=%s: %s",
                    request.server_name,
                    request.name,
                    e2,
                )
                raise
