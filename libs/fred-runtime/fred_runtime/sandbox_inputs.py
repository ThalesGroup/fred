# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Turn-bound sandbox input views; only Knowledge Flow resolves file authorization."""

from __future__ import annotations

import hashlib
import hmac
import os

import httpx
from fred_sdk.contracts.sandbox import (
    SandboxError,
    SandboxInputPort,
    SandboxSessionIdentity,
)

from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.outbound_credentials import OutboundCredentialProvider
from fred_runtime.sandbox_http import SandboxHttpAdapter


class SandboxInputHttpAdapter(SandboxInputPort):
    def __init__(
        self,
        broker: SandboxHttpAdapter,
        *,
        access_token: str | None,
        credentials: OutboundCredentialProvider | None,
    ) -> None:
        self._broker = broker
        secret = os.getenv("FRED_SANDBOX_FILE_GATEWAY_SECRET", "")
        self._bind_secret = secret.encode() if len(secret) >= 32 else None
        self._client = KfBaseClient(
            allowed_methods=frozenset({"POST"}),
            access_token=access_token,
            credentials=credentials,
        )

    async def prepare_view(self, session: SandboxSessionIdentity) -> None:
        if not session.team_id:
            raise SandboxError("invalid_request")
        if self._bind_secret is None:
            raise SandboxError("unavailable")
        try:
            key = await self._broker.view_key(session)
            payload = b"\0".join(
                (
                    b"fred-sandbox-files-bind-v1",
                    key.encode(),
                    session.session_id.encode(),
                    session.user_id.encode(),
                    session.team_id.encode(),
                )
            )
            signature = hmac.new(self._bind_secret, payload, hashlib.sha256).hexdigest()
            await self._client._request_with_token_refresh(
                method="POST",
                path=f"/sandbox-mount/views/{key}",
                phase_name="sandbox_input_prepare",
                headers={"X-Fred-Sandbox-Bind": signature},
                json={"session_id": session.session_id, "team_id": session.team_id},
            )
        except httpx.HTTPStatusError as exc:
            raise SandboxError(
                "unauthorized"
                if exc.response.status_code in {401, 403, 404}
                else "invalid_request"
                if exc.response.status_code == 400
                else "unavailable"
            ) from exc
        except httpx.HTTPError as exc:
            raise SandboxError("unavailable") from exc
