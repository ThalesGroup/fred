# Copyright Thales 2026
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

"""
Offline unit tests for `ConversationErasureService._erase_runtime_checkpoint`.

Why this file exists:
- Before this fix, the runtime's `DELETE /agents/checkpoints/{session_id}`
  returned a bare 204 with no body, so this method always recorded
  `deleted_count=None` for the `runtime_checkpoint` store in the erase
  receipt — every conversation erasure looked identical whether it purged
  one checkpoint or a hundred. The runtime now returns `{"deleted": n}`
  (fred-runtime, mirroring the sibling history-store delete); this test locks
  that the control-plane side parses it correctly.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from control_plane_backend.sessions.erasure_service import (
    STORE_CHECKPOINT,
    ConversationErasureService,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("DELETE", "http://test.invalid"),
                response=cast(Any, self),
            )


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse, *, seen: dict[str, Any]) -> None:
        self._response = response
        self._seen = seen

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def delete(self, url: str, headers: dict[str, str] | None = None):
        self._seen["url"] = url
        self._seen["headers"] = headers
        return self._response


@pytest.mark.asyncio
async def test_erase_runtime_checkpoint_records_deleted_count(monkeypatch) -> None:
    seen: dict[str, Any] = {}
    response = _FakeResponse({"deleted": 3})
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response, seen=seen),
    )

    service = ConversationErasureService(cast(Any, None))
    result = await service._erase_runtime_checkpoint(
        "http://runtime:8000/pod/v1",
        "session-1",
        "Bearer test-token",
    )

    assert result.store == STORE_CHECKPOINT
    assert result.ok is True
    assert result.deleted_count == 3
    assert seen["url"] == "http://runtime:8000/pod/v1/agents/checkpoints/session-1"
    assert seen["headers"] == {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_erase_runtime_checkpoint_defaults_to_zero_when_body_omits_deleted(
    monkeypatch,
) -> None:
    # Defensive: an older/mismatched runtime that still answers 200 with no
    # `deleted` field must not crash the erase — it records 0, not None.
    response = _FakeResponse({})
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response, seen={}),
    )

    service = ConversationErasureService(cast(Any, None))
    result = await service._erase_runtime_checkpoint(
        "http://runtime:8000/pod/v1", "session-1", "Bearer test-token"
    )

    assert result.ok is True
    assert result.deleted_count == 0
