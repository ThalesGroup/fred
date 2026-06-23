# Copyright Thales 2025
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

"""Unit tests for SessionOrchestrator._collect_new_attachments -- the filter that
decides which freshly uploaded attachments get a system note injected on a turn.

The helper only reads self.attachments_store, so we exercise it against a tiny
stub `self` rather than constructing a full orchestrator (which needs SQL stores,
KPI writers, agent factories, etc.)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest

from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.session.stores.base_session_attachment_store import (
    SessionAttachmentRecord,
)

_BASE = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _record(
    name: str, *, uid: str | None, created_at: datetime | None
) -> SessionAttachmentRecord:
    return SessionAttachmentRecord(
        session_id="sess-1",
        attachment_id=f"att-{name}",
        name=name,
        summary_md="",
        document_uid=uid,
        created_at=created_at,
    )


class _FakeStore:
    def __init__(self, records: list[SessionAttachmentRecord]):
        self._records = records

    async def list_for_session(self, session_id: str, session=None):
        assert session_id == "sess-1"
        return self._records


async def _collect(records, *, since):
    """Invoke the helper against a stub `self` carrying only attachments_store."""
    fake_self = cast(
        SessionOrchestrator, SimpleNamespace(attachments_store=_FakeStore(records))
    )
    return await SessionOrchestrator._collect_new_attachments(
        fake_self, session_id="sess-1", since=since
    )


@pytest.mark.asyncio
async def test_only_attachments_created_after_since_are_returned():
    records = [
        _record("old.pdf", uid="doc-old", created_at=_BASE - timedelta(minutes=5)),
        _record("new.pdf", uid="doc-new", created_at=_BASE + timedelta(minutes=5)),
    ]

    new = await _collect(records, since=_BASE)

    assert [r.document_uid for r in new] == ["doc-new"]


@pytest.mark.asyncio
async def test_attachment_without_document_uid_is_skipped():
    """A failed ingest has no document_uid -> the agent can't target it, so no note."""
    records = [
        _record("broken.pdf", uid=None, created_at=_BASE + timedelta(minutes=5)),
        _record("good.pdf", uid="doc-good", created_at=_BASE + timedelta(minutes=5)),
    ]

    new = await _collect(records, since=_BASE)

    assert [r.document_uid for r in new] == ["doc-good"]


@pytest.mark.asyncio
async def test_no_since_returns_all_vectorized_attachments():
    """First turn (no prior activity): every successfully ingested attachment qualifies."""
    records = [
        _record("a.pdf", uid="doc-a", created_at=_BASE),
        _record("b.pdf", uid="doc-b", created_at=_BASE),
    ]

    new = await _collect(records, since=None)

    assert {r.document_uid for r in new} == {"doc-a", "doc-b"}


@pytest.mark.asyncio
async def test_disabled_attachment_store_yields_nothing():
    fake_self = cast(SessionOrchestrator, SimpleNamespace(attachments_store=None))
    new = await SessionOrchestrator._collect_new_attachments(
        fake_self, session_id="sess-1", since=None
    )
    assert new == []


@pytest.mark.asyncio
async def test_naive_created_at_is_compared_without_error():
    """Some backends return naive datetimes; the helper must coerce, not crash."""
    naive_after = (_BASE + timedelta(minutes=5)).replace(tzinfo=None)
    records = [_record("n.pdf", uid="doc-n", created_at=naive_after)]

    new = await _collect(records, since=_BASE)

    assert [r.document_uid for r in new] == ["doc-n"]
