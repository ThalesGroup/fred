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

"""`TeamWikiAdapter` — the wire boundary a stale-write fix has to cross intact.

The bug this guards against lived exactly here: a revision read from
control-plane has to reach `propose_edit` byte-for-byte, with nothing in
between recomputing it from "whatever is current now".
"""

from __future__ import annotations

from typing import Any

import pytest
from fred_runtime.integrations.v2_runtime.adapters import TeamWikiAdapter
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.content = b"1"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _RecordingClient:
    def __init__(self, response_payload: Any) -> None:
        self._response_payload = response_payload
        self.last_call: dict[str, Any] | None = None

    async def request(
        self, method: str, url: str, *, headers: dict[str, str], json: Any = None
    ) -> _FakeResponse:
        self.last_call = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }
        return _FakeResponse(self._response_payload)


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1", team_id="team-1", access_token="tok"
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _adapter(client: _RecordingClient) -> TeamWikiAdapter:
    return TeamWikiAdapter(
        binding=_binding(),
        control_plane_url="https://control-plane.internal",
        http_client=client,
    )


async def test_read_page_preserves_the_revision_id_exactly() -> None:
    """The one field this correction added to the read side. It must survive
    the JSON round-trip unchanged — a stray strip/cast here would silently
    reintroduce the bug one layer up."""

    client = _RecordingClient(
        {
            "page": {"slug": "p", "title": "P"},
            "content_md": "body",
            "revision_id": "rev-abc123",
        }
    )
    adapter = _adapter(client)

    page = await adapter.read_page("p")

    assert page.revision_id == "rev-abc123"


async def test_propose_edit_sends_the_base_revision_id_verbatim() -> None:
    """What the capability read must be exactly what reaches control-plane —
    no re-derivation, no default, no silent substitution of "current"."""

    client = _RecordingClient({"proposal_id": "prop-1", "title": "P", "slug": "p"})
    adapter = _adapter(client)

    await adapter.propose_edit(
        slug="p", content_md="new text", base_revision_id="rev-abc123"
    )

    assert client.last_call is not None
    assert client.last_call["json"]["base_revision_id"] == "rev-abc123"
    assert client.last_call["url"].endswith("/proposals/edit")
