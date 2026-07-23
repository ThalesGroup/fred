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

"""Edit-notification (`abefore_model`) and open-documents catalog (`awrap_model_call`).

The durable `agent_notified_at` flag replaces Kea's orchestrator last-activity diff:
a user-edited-and-unnotified document injects the system note exactly once.
"""

from __future__ import annotations

import pytest
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.capability import _WritableDocumentMiddleware
from fred_capability_writable_document.store import WritableDocumentRecord
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.messages import SystemMessage
from port_fakes import FakeWritableDocumentStore


@pytest.fixture()
def fake_store() -> FakeWritableDocumentStore:
    fake = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: fake)
    try:
        yield fake
    finally:
        store_module.clear_store_provider()


def _middleware(session_id: str | None = "s-1") -> _WritableDocumentMiddleware:
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id=session_id),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    return _WritableDocumentMiddleware(ctx)


async def _seed_user_edit(fake: FakeWritableDocumentStore) -> None:
    await fake.upsert(
        WritableDocumentRecord(
            session_id="s-1",
            document_id="doc-1",
            user_id="u-1",
            title="Report",
            content_md="edited by user",
            updated_by="user",
            agent_notified_at=None,
        )
    )


@pytest.mark.asyncio
async def test_abefore_model_notes_user_edit_once(
    fake_store: FakeWritableDocumentStore,
):
    await _seed_user_edit(fake_store)
    middleware = _middleware()

    update = await middleware.abefore_model({}, None)
    assert update is not None
    messages = update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], SystemMessage)
    note = str(messages[0].content)
    assert "The user edited the document 'Report' (id=doc-1)" in note
    assert "edited by user" in note
    # Marked notified so it never fires again.
    assert fake_store.notified_calls and fake_store.notified_calls[0][:2] == (
        "s-1",
        "doc-1",
    )

    # Second turn: nothing pending -> no state update.
    assert await middleware.abefore_model({}, None) is None


@pytest.mark.asyncio
async def test_abefore_model_ignores_agent_authored_documents(
    fake_store: FakeWritableDocumentStore,
):
    await fake_store.upsert(
        WritableDocumentRecord(
            session_id="s-1",
            document_id="doc-agent",
            user_id="u-1",
            title="Agent doc",
            content_md="agent wrote this",
            updated_by="agent",
        )
    )
    assert await _middleware().abefore_model({}, None) is None


@pytest.mark.asyncio
async def test_abefore_model_no_session_returns_none(
    fake_store: FakeWritableDocumentStore,
):
    await _seed_user_edit(fake_store)
    assert await _middleware(session_id=None).abefore_model({}, None) is None


class _FakeRequest:
    """Minimal `ModelRequest` stand-in: reads `system_prompt`, captures `override`."""

    def __init__(self, system_prompt: str | None) -> None:
        self.system_prompt = system_prompt
        self.overridden: SystemMessage | None = None

    def override(self, *, system_message: SystemMessage) -> "_FakeRequest":
        self.overridden = system_message
        return self


@pytest.mark.asyncio
async def test_awrap_model_call_overlays_open_documents_catalog(
    fake_store: FakeWritableDocumentStore,
):
    await fake_store.upsert(
        WritableDocumentRecord(
            session_id="s-1",
            document_id="doc-1",
            user_id="u-1",
            title="Report",
            content_md="body",
            updated_by="agent",
        )
    )
    middleware = _middleware()
    request = _FakeRequest("BASE PROMPT")

    async def handler(req: _FakeRequest) -> _FakeRequest:
        return req

    result = await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]

    assert result.overridden is not None
    merged = str(result.overridden.content)
    assert "BASE PROMPT" in merged
    assert "WRITABLE DOCUMENT" in merged
    assert "Collaborative documents already open in the editor" in merged
    assert "- 'Report' (document_id=doc-1)" in merged


@pytest.mark.asyncio
async def test_awrap_model_call_overlays_write_instructions_without_documents(
    fake_store: FakeWritableDocumentStore,
):
    middleware = _middleware()
    request = _FakeRequest("BASE PROMPT")

    async def handler(req: _FakeRequest) -> _FakeRequest:
        return req

    await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]
    # No documents in the session -> the write instructions are still overlaid
    # (so "write me a report" triggers the tool), but no catalog fragment.
    # The fake's `override` mutates the request in place, so assert on it.
    assert request.overridden is not None
    merged = str(request.overridden.content)
    assert merged.startswith("BASE PROMPT")
    assert "write_document" in merged
    assert "Collaborative documents already open in the editor" not in merged
