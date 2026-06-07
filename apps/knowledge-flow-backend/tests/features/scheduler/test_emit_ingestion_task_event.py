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

"""Unit tests for emit_ingestion_task_event — OPS-04 target propagation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fred_core.tasks.models import IngestionTaskEvent

from knowledge_flow_backend.features.scheduler.activities import emit_ingestion_task_event


def _run(coro):
    return asyncio.run(coro)


def _make_mock_context() -> tuple[MagicMock, list[IngestionTaskEvent]]:
    """Return (mock app context, list that captures recorded events)."""
    recorded: list[IngestionTaskEvent] = []

    async def _record(event: IngestionTaskEvent) -> None:
        recorded.append(event)

    task_service = MagicMock()
    task_service.record = AsyncMock(side_effect=_record)

    app_ctx = MagicMock()
    app_ctx.get_task_service.return_value = task_service

    return app_ctx, recorded


# ApplicationContext is imported inside the function body, so patch at its source.
_PATCH_CTX = "knowledge_flow_backend.application_context.ApplicationContext.get_instance"


# ── target propagation ────────────────────────────────────────────────────────


def test_target_populated_when_document_uid_provided():
    app_ctx, recorded = _make_mock_context()
    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(
            emit_ingestion_task_event(
                task_id="t1",
                state="running",
                step="processing",
                document_uid="doc-abc",
                display_name="report.pdf",
            )
        )

    assert len(recorded) == 1
    event = recorded[0]
    assert isinstance(event, IngestionTaskEvent)
    assert event.target is not None
    assert event.target.type == "document"
    assert event.target.id == "doc-abc"
    assert event.target.label == "report.pdf"


def test_target_uses_document_uid_as_label_fallback_when_display_name_absent():
    app_ctx, recorded = _make_mock_context()
    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(
            emit_ingestion_task_event(
                task_id="t1",
                state="running",
                document_uid="doc-xyz",
                display_name=None,
            )
        )

    event = recorded[0]
    assert event.target is not None
    assert event.target.id == "doc-xyz"
    assert event.target.label == "doc-xyz"


def test_target_is_none_when_no_document_uid():
    app_ctx, recorded = _make_mock_context()
    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(
            emit_ingestion_task_event(
                task_id="t1",
                state="succeeded",
            )
        )

    event = recorded[0]
    assert event.target is None


# ── state and detail fields pass through unchanged ────────────────────────────


def test_state_and_detail_pass_through():
    app_ctx, recorded = _make_mock_context()
    with patch(_PATCH_CTX, return_value=app_ctx):
        _run(
            emit_ingestion_task_event(
                task_id="t2",
                state="failed",
                error="disk full",
                progress=0.4,
                step="vectorising",
                processed=3,
                total=10,
                failed=1,
            )
        )

    event = recorded[0]
    assert event.state.value == "failed"
    assert event.error == "disk full"
    assert event.progress == 0.4
    assert event.step == "vectorising"
    assert event.detail is not None
    assert event.detail.processed == 3
    assert event.detail.total == 10
    assert event.detail.failed == 1
