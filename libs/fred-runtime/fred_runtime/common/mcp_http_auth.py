"""Per-request MCP HTTP credentials for FastMCP's public client transport."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx2
from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.logs.propagation import CONTEXT_HEADER, outbound_context_headers

from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    OutboundCredentialProvider,
)
from fred_runtime.common.structures import TokenRefreshCallback, resolve_refresh_result
from fred_runtime.common.token_expiry import is_expired_httpx_response
from fred_runtime.runtime_support.authority import AuthorityLostError


class MCPHTTPAuth(httpx2.Auth):
    """Read the current bearer and grant before every MCP HTTP request."""

    requires_request_body = True

    def __init__(
        self,
        provider: OutboundCredentialProvider,
        *,
        refresh: TokenRefreshCallback | None = None,
        refresh_owner: object | None = None,
    ) -> None:
        self._provider = provider
        self._refresh = refresh
        self._refresh_owner = refresh_owner or self

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        await request.aread()
        request.headers.pop(CONTEXT_HEADER, None)
        if isinstance(self._provider, DelegatedCredentialProvider):
            await self._provider.credentials()
            lease = await self._provider.get_token_lease()
            request.headers["Authorization"] = f"Bearer {lease.token}"
            request.headers.update(outbound_context_headers())
            response = yield request
            if response.status_code == 401:
                await response.aread()
                await response.aclose()
                replacement = await self._provider.refresh_rejected(lease)
                request.headers["Authorization"] = f"Bearer {replacement.token}"
                response = yield request
            if _authority_refused(response):
                raise AuthorityLostError() from None
            return

        credentials = await self._provider.credentials()
        if credentials.authorization:
            request.headers["Authorization"] = credentials.authorization
        else:
            request.headers.pop("Authorization", None)
        response = yield request
        if self._refresh is not None and response.status_code == 401:
            await response.aread()
            if is_expired_httpx_response(response):
                await response.aclose()
                new_token = await resolve_refresh_result(
                    self._refresh(), self._refresh_owner
                )
                if not new_token:
                    raise RuntimeError("MCP token refresh returned no token.")
                request.headers["Authorization"] = f"Bearer {new_token}"
                yield request


def _authority_refused(response: httpx2.Response) -> bool:
    return response.status_code in (401, 403) or (
        response.status_code == 503
        and response.headers.get(DENIAL_CAUSE_HEADER)
        == ACCOUNT_STATUS_UNAVAILABLE_CAUSE
    )
