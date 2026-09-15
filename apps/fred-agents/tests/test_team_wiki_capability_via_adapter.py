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
`TeamWikiAdapter` (fred-runtime) driven through `TeamWikiCapability`'s real
tools (fred-capability-team-wiki), wired the way `agent_app.py` wires them in
production, against a simulated control-plane HTTP client.

Why this test exists: `libs/fred-runtime/tests/test_team_wiki_adapter.py` pins
the adapter against a fake HTTP client; `libs/fred-capability-team-wiki/tests/
test_team_wiki.py` pins the capability against a fake `TeamWikiPort`. Neither
proves the two layers AGREE on when a cached snapshot renews after a conflict
and when read coverage resets to a newly-read revision — the exact seam the
conflict-recovery correction crosses. This file has no dependency on the
capability's own port fake or the adapter's own client fake; it constructs
both real classes and drives them together, so a disagreement between the two
layers would fail here even with each layer's own tests green.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fred_capability_team_wiki.wiki.capability import (
    TeamWikiCapability,
    TeamWikiConfig,
)
from fred_runtime.integrations.v2_runtime.adapters import TeamWikiAdapter
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import RuntimeServices


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.content = b"1"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _ScriptedClient:
    """One queued response per call, in order. A queued `httpx.Response` is
    returned as-is, so its own `raise_for_status()` raises a real
    `httpx.HTTPStatusError` for a genuine 409 partway through the sequence —
    same convention as `test_team_wiki_adapter.py`'s fake of the same name."""

    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, Any]] = []

    async def request(
        self, method: str, url: str, *, headers: dict[str, str], json: Any = None
    ) -> Any:
        self.calls.append({"method": method, "url": url, "json": json})
        item = self._payloads.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return _FakeResponse(item)


def _conflict_response(
    *, current_revision_id: str, current_content_md: str
) -> httpx.Response:
    return httpx.Response(
        409,
        json={
            "detail": "the page changed since you read it",
            "current_revision_id": current_revision_id,
            "current_content_md": current_content_md,
        },
        request=httpx.Request("POST", "https://control-plane.internal/x"),
    )


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


def _wired_tools(client: Any) -> dict[str, Any]:
    """One turn: a real `TeamWikiAdapter` bound to `client`, injected into a
    real `TeamWikiCapability` exactly as `RuntimeServices.team_wiki` is in
    production — same per-turn adapter instance and capability closure for
    every tool call the test makes."""

    adapter = TeamWikiAdapter(
        binding=_binding(),
        control_plane_url="https://control-plane.internal",
        http_client=client,
    )
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=TeamWikiConfig(mode="read_write"),
        turn_options=EmptyModel(),
        services=RuntimeServices(team_wiki=adapter),
    )
    return {t.name: t for t in TeamWikiCapability().tools(ctx)}


def _call(tools: dict[str, Any], name: str, args: dict[str, Any]) -> Any:
    return asyncio.run(
        tools[name].ainvoke(
            {"type": "tool_call", "name": name, "args": args, "id": "c1"}
        )
    )


def test_conflict_recovery_across_the_real_adapter_and_capability() -> None:
    """A1, end to end: GET A, propose against A -> 409 (B landed on the
    server meanwhile), a fresh read-from-zero must issue a real GET and see
    B, and only then does a propose succeed — anchored to B, never replaying
    the adapter's pre-conflict snapshot of A."""

    client = _ScriptedClient(
        [
            {"pages": [{"page_id": "p1", "slug": "s1", "title": "S", "kind": "page"}]},
            {
                "page": {"slug": "s1", "title": "S"},
                "content_md": "A",
                "revision_id": "rev-A",
            },
            _conflict_response(current_revision_id="rev-B", current_content_md="B"),
            {
                "page": {"slug": "s1", "title": "S"},
                "content_md": "B",
                "revision_id": "rev-B",
            },
            {"proposal_id": "prop-1", "title": "S", "slug": "s1"},
        ]
    )
    tools = _wired_tools(client)

    first_read = _call(tools, "wiki_read_page", {"path": "S"})
    assert "A" in first_read.content

    conflict = _call(
        tools, "wiki_propose_page_text", {"path": "S", "content_md": "new-A"}
    )
    assert conflict.artifact.is_error is True

    second_read = _call(tools, "wiki_read_page", {"path": "S"})
    assert "B" in second_read.content

    ok = _call(tools, "wiki_propose_page_text", {"path": "S", "content_md": "new-B"})
    assert ok.artifact.is_error is False

    # The actual HTTP calls and the revisions that crossed the wire, not just
    # the tool-facing outcome — a fix that renews the snapshot without
    # actually sending base_revision_id="rev-B" would still pass on content
    # alone.
    propose_calls = [c for c in client.calls if c["url"].endswith("/proposals/edit")]
    assert [c["json"]["base_revision_id"] for c in propose_calls] == [
        "rev-A",
        "rev-B",
    ]
    read_calls = [c for c in client.calls if c["url"].endswith("/pages/s1")]
    assert len(read_calls) == 2  # the conflict forced a real second GET, not a replay
