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

"""Chat-time `write_document` tool tests (#1905).

The tool is built from a typed `CapabilityContext` whose identity carries the
session/user; the store is substituted with an in-memory fake through the
overridable provider so the whole path runs offline.
"""

from __future__ import annotations

import pytest
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.capability import (
    WritableDocumentPart,
    _WritableDocumentMiddleware,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeWritableDocumentStore


@pytest.fixture()
def fake_store() -> FakeWritableDocumentStore:
    fake = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: fake)
    try:
        yield fake
    finally:
        store_module.clear_store_provider()


def _tool(session_id: str | None = "s-1", user_id: str = "u-1"):
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id=user_id, session_id=session_id),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    middleware = _WritableDocumentMiddleware(ctx)
    return middleware.tools[0]


@pytest.mark.asyncio
async def test_create_new_document_emits_part(fake_store: FakeWritableDocumentStore):
    content, artifact = await _tool().coroutine(
        title="Weekly report", content_markdown="# Report\n\nBody"
    )

    assert "saved (id=" in content
    assert len(artifact.ui_parts) == 1
    part = artifact.ui_parts[0]
    assert isinstance(part, WritableDocumentPart)
    assert part.type == "writable_document"
    assert part.title == "Weekly report"
    assert part.content_md == "# Report\n\nBody"
    assert part.updated_by == "agent"

    # Persisted under the session with the closure's user id.
    stored = await fake_store.list_for_session("s-1")
    assert len(stored) == 1
    assert stored[0].user_id == "u-1"
    assert stored[0].document_id == part.document_id


@pytest.mark.asyncio
async def test_revise_in_place_reuses_document_id(
    fake_store: FakeWritableDocumentStore,
):
    tool = _tool()
    _c1, a1 = await tool.coroutine(title="Doc", content_markdown="v1")
    doc_id = a1.ui_parts[0].document_id

    _c2, a2 = await tool.coroutine(
        title="Doc", content_markdown="v2 revised", document_id=doc_id
    )

    assert a2.ui_parts[0].document_id == doc_id
    assert a2.ui_parts[0].content_md == "v2 revised"
    # One row, revised in place (no duplicate editor tab).
    rows = await fake_store.list_for_session("s-1")
    assert len(rows) == 1
    assert rows[0].content_md == "v2 revised"


@pytest.mark.asyncio
async def test_title_dedup_revises_without_document_id(
    fake_store: FakeWritableDocumentStore,
):
    tool = _tool()
    _c1, a1 = await tool.coroutine(title="Same title", content_markdown="first")
    doc_id = a1.ui_parts[0].document_id

    # Same exact title, document_id omitted -> revise the existing one, not duplicate.
    _c2, a2 = await tool.coroutine(title="Same title", content_markdown="second")

    assert a2.ui_parts[0].document_id == doc_id
    rows = await fake_store.list_for_session("s-1")
    assert len(rows) == 1
    assert rows[0].content_md == "second"


@pytest.mark.asyncio
async def test_no_session_returns_graceful_error(
    fake_store: FakeWritableDocumentStore,
):
    content, artifact = await _tool(session_id=None).coroutine(
        title="X", content_markdown="Y"
    )

    assert "no active session" in content.lower()
    assert artifact.is_error is True
    assert artifact.ui_parts == ()
    # Nothing persisted.
    assert await fake_store.list_for_session("s-1") == []
