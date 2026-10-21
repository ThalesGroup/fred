# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Broker transport for code execution; no backend credential reaches the tool."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx
from fred_sdk.contracts.sandbox import (
    SandboxError,
    SandboxExecutionPort,
    SandboxRequest,
    SandboxResult,
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

    async def execute(self, request: SandboxRequest) -> SandboxResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/execute",
                headers={"Authorization": f"Bearer {self._token}"},
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

    async def aclose(self) -> None:
        await self._client.aclose()
