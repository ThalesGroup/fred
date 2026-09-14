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

import httpx
import pytest
from fred_runtime.integrations.v2_runtime.adapters import TeamWikiAdapter
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import TeamWikiPortError

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
        self.call_count = 0

    async def request(
        self, method: str, url: str, *, headers: dict[str, str], json: Any = None
    ) -> _FakeResponse:
        self.call_count += 1
        self.last_call = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }
        return _FakeResponse(self._response_payload)


class _ScriptedClient:
    """Returns one queued payload per call, in order — for a test that needs
    control-plane state to change between two calls on the same adapter.

    A queued `httpx.Response` is returned as-is rather than wrapped, so its
    own `raise_for_status()` raises a real `httpx.HTTPStatusError` — for a
    test that needs a genuine server error (e.g. a 409) partway through a
    scripted sequence.
    """

    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = list(payloads)

    async def request(
        self, method: str, url: str, *, headers: dict[str, str], json: Any = None
    ) -> Any:
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


def _adapter(client: Any) -> TeamWikiAdapter:
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


async def test_read_page_slices_the_requested_window() -> None:
    """The control-plane GET has no window parameters — it always returns the
    page whole — so the adapter is the one place the `[offset:offset+max_chars]`
    contract has to hold, same as `DocumentMarkdownPort`'s adapters."""

    client = _RecordingClient(
        {
            "page": {"slug": "p", "title": "P"},
            "content_md": "0123456789",
            "revision_id": "rev-1",
        }
    )
    adapter = _adapter(client)

    page = await adapter.read_page("p", max_chars=4, offset=3)

    assert page.content_md == "3456"
    assert page.offset == 3
    assert page.next_offset == 7
    assert page.total_chars == 10
    assert page.truncated is True


async def test_read_page_reports_no_continuation_at_the_end() -> None:
    client = _RecordingClient(
        {
            "page": {"slug": "p", "title": "P"},
            "content_md": "0123456789",
            "revision_id": "rev-1",
        }
    )
    adapter = _adapter(client)

    page = await adapter.read_page("p", max_chars=4, offset=8)

    assert page.content_md == "89"
    assert page.next_offset is None
    assert page.truncated is False


async def test_read_page_fetches_a_slug_once_per_turn() -> None:
    """A long page read across several continuation calls must not re-fetch
    and re-parse the whole page on every one of them — the same doctrine as
    `DocumentMarkdownAdapter` (DOCREAD-01): one control-plane round trip per
    slug per turn, not one per segment."""

    client = _RecordingClient(
        {
            "page": {"slug": "p", "title": "P"},
            "content_md": "0123456789",
            "revision_id": "rev-1",
        }
    )
    adapter = _adapter(client)

    first = await adapter.read_page("p", max_chars=4, offset=0)
    second = await adapter.read_page("p", max_chars=4, offset=4)

    assert client.call_count == 1
    assert first.content_md == "0123"
    assert second.content_md == "4567"
    assert second.revision_id == first.revision_id


async def test_read_page_cache_is_cleared_on_rebind() -> None:
    """A new turn must never see a page pinned by a previous one."""

    client = _RecordingClient(
        {
            "page": {"slug": "p", "title": "P"},
            "content_md": "0123456789",
            "revision_id": "rev-1",
        }
    )
    adapter = _adapter(client)
    await adapter.read_page("p")

    adapter.rebind(_binding())
    await adapter.read_page("p")

    assert client.call_count == 2


async def test_publish_proposal_invalidates_the_page_cache() -> None:
    """A same-turn re-read after this adapter's own publish must see what was
    just written, not the snapshot `read_page` cached before the publish."""

    client = _ScriptedClient(
        [
            {
                "page": {"slug": "p", "title": "P"},
                "content_md": "old",
                "revision_id": "rev-1",
            },
            {"page": {"slug": "p"}},
            {
                "page": {"slug": "p", "title": "P"},
                "content_md": "new",
                "revision_id": "rev-2",
            },
        ]
    )
    adapter = _adapter(client)

    before = await adapter.read_page("p")
    slug = await adapter.publish_proposal("prop-1")
    after = await adapter.read_page("p")

    assert before.content_md == "old"
    assert slug == "p"
    assert after.content_md == "new"
    assert after.revision_id == "rev-2"


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


async def test_a_conflict_on_propose_edit_evicts_the_cache_so_the_next_read_renews_it() -> (
    None
):
    """A1: GET A, propose against A, server 409s (B landed meanwhile). A
    caller told to "read again from the start" must reach the server, not
    replay the pinned snapshot the rejected proposal was anchored to."""

    client = _ScriptedClient(
        [
            {
                "page": {"slug": "p", "title": "P"},
                "content_md": "A",
                "revision_id": "rev-A",
            },
            _conflict_response(current_revision_id="rev-B", current_content_md="B"),
            {
                "page": {"slug": "p", "title": "P"},
                "content_md": "B",
                "revision_id": "rev-B",
            },
        ]
    )
    adapter = _adapter(client)

    first = await adapter.read_page("p")
    assert first.revision_id == "rev-A"

    with pytest.raises(TeamWikiPortError) as excinfo:
        await adapter.propose_edit(
            slug="p", content_md="based on A", base_revision_id="rev-A"
        )
    assert excinfo.value.status_code == 409

    second = await adapter.read_page("p")
    assert second.revision_id == "rev-B"
    assert second.content_md == "B"


async def test_a_conflict_on_a_different_slug_leaves_this_ones_cache_alone() -> None:
    """Eviction on 409 is scoped to the slug that conflicted — a sibling
    page's already-cached snapshot must survive it untouched. Only two
    responses are queued: a third real fetch (were "other" wrongly evicted
    too) would raise on the empty queue rather than silently pass."""

    client = _ScriptedClient(
        [
            {
                "page": {"slug": "other", "title": "Other"},
                "content_md": "unrelated",
                "revision_id": "rev-1",
            },
            _conflict_response(current_revision_id="rev-2", current_content_md="p2"),
        ]
    )
    adapter = _adapter(client)

    cached = await adapter.read_page("other")
    with pytest.raises(TeamWikiPortError):
        await adapter.propose_edit(slug="p", content_md="new", base_revision_id="rev-1")

    again = await adapter.read_page("other")
    assert again.content_md == cached.content_md
