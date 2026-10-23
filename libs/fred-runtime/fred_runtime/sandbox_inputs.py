# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Turn-bound input selection; only Knowledge Flow resolves file authorization."""

from __future__ import annotations

import hashlib
import hmac
import os
import httpx
from pathlib import PurePosixPath
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

    async def bind_corpus(
        self, document_uid: str, session: SandboxSessionIdentity
    ) -> str:
        return await self._bind("corpus", "document_uid", document_uid, session)

    async def bind_attachment(
        self, attachment_id: str, session: SandboxSessionIdentity
    ) -> str:
        return await self._bind("attachments", "attachment_id", attachment_id, session)

    async def _bind(
        self, kind: str, field: str, source_id: str, session: SandboxSessionIdentity
    ) -> str:
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
            response = await self._client._request_with_token_refresh(
                method="POST",
                path=f"/sandbox-mount/views/{key}/{kind}",
                phase_name="sandbox_input_bind",
                headers={"X-Fred-Sandbox-Bind": signature},
                json={
                    "session_id": session.session_id,
                    "team_id": session.team_id,
                    field: source_id,
                },
            )
            path = response.json()["path"]
            if (
                not isinstance(path, str)
                or not path.startswith("/inputs/")
                or any(part in {"", ".", ".."} for part in path.split("/")[2:])
                or "\\" in path
                or "\x00" in path
                or str(PurePosixPath(path)) != path
            ):
                raise ValueError("Invalid mounted source path")
            return path
        except httpx.HTTPStatusError as exc:
            raise SandboxError(
                "unauthorized"
                if exc.response.status_code in {401, 403, 404}
                else "invalid_request"
                if exc.response.status_code == 400
                else "unavailable"
            ) from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise SandboxError("unavailable") from exc
