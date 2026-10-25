# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Broker transport for code execution; no backend credential reaches the tool."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from urllib.parse import urlsplit

import httpx
from fred_sdk.contracts.sandbox import (
    SandboxError,
    SandboxExecutionPort,
    SandboxRequest,
    SandboxResult,
    SandboxSessionIdentity,
)


class SandboxHttpAdapter(SandboxExecutionPort):
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Invalid sandbox broker URL")
        if parsed.scheme != "https" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Sandbox broker URL requires HTTPS outside loopback")
        if not token or len(token) < 32:
            raise ValueError("Sandbox broker token must have at least 32 characters")
        self._base_url = base_url.rstrip("/")
        self._token = token
        # Cover the broker's maximum cold preparation plus execution deadlines.
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(480.0, connect=5.0),
        )

    @classmethod
    def from_environment(cls) -> SandboxHttpAdapter | None:
        url = os.getenv("FRED_SANDBOX_BROKER_URL")
        token = os.getenv("FRED_SANDBOX_BROKER_TOKEN")
        if not url and not token:
            return None
        if not url or not token:
            raise ValueError("Both sandbox broker URL and token are required")
        return cls(base_url=url, token=token)

    async def execute(
        self, request: SandboxRequest, session: SandboxSessionIdentity | None = None
    ) -> SandboxResult:
        headers = {"Authorization": f"Bearer {self._token}"}
        if session is not None:
            headers["X-Fred-Sandbox-Session"] = self.session_key(session)
            headers["X-Fred-Sandbox-Tenant"] = self.tenant_key(session)
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/execute",
                headers=headers,
                json=request.model_dump(),
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise SandboxError("unavailable") from exc
        if response.status_code != 200:
            try:
                code = response.json()["error_code"]
            except (ValueError, KeyError, TypeError):
                code = "unavailable"
            raise SandboxError(code)
        try:
            return SandboxResult.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            raise SandboxError("invalid_response") from exc

    def session_key(self, session: SandboxSessionIdentity) -> str:
        payload = json.dumps(
            session.model_dump(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hmac.new(
            self._token.encode(),
            b"fred-sandbox-session-v1\0" + payload,
            hashlib.sha256,
        ).hexdigest()

    def tenant_key(self, session: SandboxSessionIdentity) -> str:
        scope = f"team:{session.team_id}" if session.team_id else f"user:{session.user_id}"
        return hmac.new(
            self._token.encode(),
            b"fred-sandbox-tenant-v1\0" + scope.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def view_key(self, session: SandboxSessionIdentity) -> str:
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/view-key",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "X-Fred-Sandbox-Session": self.session_key(session),
                    "X-Fred-Sandbox-Tenant": self.tenant_key(session),
                },
            )
            response.raise_for_status()
            key = response.json()["view_key"]
            if (
                not isinstance(key, str)
                or len(key) != 64
                or any(character not in "0123456789abcdef" for character in key)
            ):
                raise ValueError("Invalid sandbox view key")
            return key
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise SandboxError("unavailable") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
