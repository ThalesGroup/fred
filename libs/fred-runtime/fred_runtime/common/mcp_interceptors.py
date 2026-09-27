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


"""MCP tool call interceptors (retry, auth refresh, etc.)."""

from __future__ import annotations

import logging
from typing import AbstractSet, Awaitable, Callable

import httpx
from fred_core.common.fastapi_handlers import (
    DENIAL_CAUSE_HEADER,
    STANDING_UNAVAILABLE_CAUSE,
)
from fred_sdk.contracts.runtime import unwrap_run_stop_error
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult

from fred_runtime.common.outbound_credentials import OutboundCredentialProvider
from fred_runtime.common.structures import TokenRefreshCallback, resolve_refresh_result
from fred_runtime.common.token_expiry import (
    is_expired_httpx_status_error,
    unwrap_httpx_status_error,
)
from fred_runtime.runtime_support.authority import AuthorityLostError

logger = logging.getLogger(__name__)

# A receiver's refusal of the run's authority. Anything else is a transport or
# tool fault and keeps its existing handling.
AUTHORITY_REFUSED_STATUSES = (401, 403)


class DelegatedAuthorityInterceptor:
    """Intercepts MCP tool calls made under delegation.

    Two jobs: put a current workload bearer on every call, so a connection that
    outlives one token keeps working; and end the run when a receiver refuses
    this run's authority, rather than asking again with another credential.
    """

    def __init__(
        self,
        provider: OutboundCredentialProvider,
        *,
        delegated_server_ids: AbstractSet[str],
    ):
        self._provider = provider
        self._delegated_server_ids = frozenset(delegated_server_ids)

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable],
    ):
        if request.server_name not in self._delegated_server_ids:
            return await handler(request)

        credentials = await self._provider.credentials()
        headers = dict(request.headers or {})
        if credentials.authorization:
            headers["Authorization"] = credentials.authorization
        call = request.override(headers=headers)

        try:
            result = await handler(call)
            if (
                isinstance(result, CallToolResult)
                and result.isError
                and result.structuredContent == {"cause": "authority_lost"}
            ):
                raise AuthorityLostError() from None
            return result
        except AuthorityLostError:
            raise
        except Exception as e:  # noqa: BLE001
            run_stop = unwrap_run_stop_error(e)
            if run_stop is not None:
                raise run_stop from None
            http_err: httpx.HTTPStatusError | None = unwrap_httpx_status_error(e)
            status = (
                http_err.response.status_code
                if http_err is not None and http_err.response is not None
                else None
            )
            if status not in AUTHORITY_REFUSED_STATUSES and not (
                status == 503
                and http_err is not None
                and http_err.response.headers.get(DENIAL_CAUSE_HEADER)
                == STANDING_UNAVAILABLE_CAUSE
            ):
                raise
            logger.error(
                "[MCP] event=tool_call outcome=stopped reason=authority_refused status=%s",
                status,
            )
            # `from None` on purpose: the receiver's body must not reach a
            # traceback, an event or the transcript.
            raise AuthorityLostError() from None


class LivePersonBearerInterceptor:
    """Read the current own-identity bearer for each authenticated tool call."""

    def __init__(
        self,
        provider: OutboundCredentialProvider,
        *,
        authenticated_server_ids: AbstractSet[str],
    ) -> None:
        self._provider = provider
        self._authenticated_server_ids = frozenset(authenticated_server_ids)

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable],
    ):
        if request.server_name not in self._authenticated_server_ids:
            return await handler(request)
        credentials = await self._provider.credentials()
        headers = dict(request.headers or {})
        if credentials.authorization:
            headers["Authorization"] = credentials.authorization
        return await handler(request.override(headers=headers))


class ExpiredTokenRetryInterceptor:
    """Refresh an expired person token and retry an MCP tool call once."""

    def __init__(self, refresh_token_cb: TokenRefreshCallback):
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
                "[MCP] event=tool_call outcome=retrying reason=expired_token"
            )

            try:
                new_token = await resolve_refresh_result(self._refresh(), self)
            except Exception:  # noqa: BLE001
                logger.error(
                    "[MCP] event=token_refresh outcome=failed reason=refresh_error"
                )
                raise

            if not new_token:
                logger.error(
                    "[MCP] event=token_refresh outcome=failed reason=empty_token"
                )
                raise

            new_headers = dict(request.headers or {})
            new_headers["Authorization"] = f"Bearer {new_token}"
            retry_req = request.override(headers=new_headers)

            try:
                return await handler(retry_req)
            except Exception:  # noqa: BLE001
                logger.error("[MCP] event=tool_call outcome=failed reason=retry_failed")
                raise
