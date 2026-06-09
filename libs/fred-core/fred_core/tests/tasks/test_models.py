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

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from fred_core.tasks.models import (
    IngestionDetail,
    IngestionTaskEvent,
    StartIngestionRequest,
    StartTaskRequest,
    TaskEvent,
    TaskLogDetail,
    TaskLogEvent,
    TaskState,
    TaskTarget,
)

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)

_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)
_REQUEST_ADAPTER: TypeAdapter[StartTaskRequest] = TypeAdapter(StartTaskRequest)


# ── TaskState ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "state,expected",
    [
        (TaskState.succeeded, True),
        (TaskState.failed, True),
        (TaskState.cancelled, True),
        (TaskState.pending, False),
        (TaskState.running, False),
        (TaskState.cancelling, False),
    ],
)
def test_task_state_is_terminal(state: TaskState, expected: bool) -> None:
    assert state.is_terminal is expected


# ── TaskEvent discriminated union ─────────────────────────────────────────────


def test_ingestion_task_event_round_trips() -> None:
    event = IngestionTaskEvent(
        task_id="xyz",
        state=TaskState.succeeded,
        seq=5,
        timestamp=_NOW,
        detail=IngestionDetail(
            processed=10,
            total=10,
            failed=0,
            preview=10,
            vectorized=10,
            sql_indexed=8,
        ),
    )
    parsed = _EVENT_ADAPTER.validate_python(event.model_dump())
    assert isinstance(parsed, IngestionTaskEvent)
    assert parsed.state.is_terminal


def test_log_task_event_round_trips() -> None:
    event = TaskLogEvent(
        task_id="abc",
        state=TaskState.running,
        seq=2,
        timestamp=_NOW,
        detail=TaskLogDetail(level="warn", message="slow step"),
    )
    parsed = _EVENT_ADAPTER.validate_python(event.model_dump())
    assert isinstance(parsed, TaskLogEvent)
    assert parsed.detail.level == "warn"


def test_ingestion_task_event_with_target_round_trips() -> None:
    event = IngestionTaskEvent(
        task_id="xyz",
        state=TaskState.running,
        seq=1,
        timestamp=_NOW,
        target=TaskTarget(type="document", id="doc-42", label="report.pdf"),
        owner="user-99",
    )
    parsed = _EVENT_ADAPTER.validate_python(event.model_dump())
    assert isinstance(parsed, IngestionTaskEvent)
    assert parsed.target is not None
    assert parsed.target.type == "document"
    assert parsed.target.id == "doc-42"
    assert parsed.target.label == "report.pdf"
    assert parsed.owner == "user-99"


def test_ingestion_task_event_target_is_optional() -> None:
    """Existing events without target stay valid (backwards compat)."""
    event = IngestionTaskEvent(
        task_id="xyz",
        state=TaskState.succeeded,
        seq=5,
        timestamp=_NOW,
    )
    parsed = _EVENT_ADAPTER.validate_python(event.model_dump())
    assert isinstance(parsed, IngestionTaskEvent)
    assert parsed.target is None
    assert parsed.owner is None


def test_task_event_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        _EVENT_ADAPTER.validate_python(
            {
                "task_id": "x",
                "kind": "unknown",
                "state": "running",
                "seq": 0,
                "timestamp": _NOW.isoformat(),
            }
        )


# ── StartTaskRequest ──────────────────────────────────────────────────────────


def test_start_ingestion_request_parses() -> None:
    req = _REQUEST_ADAPTER.validate_python(
        {"kind": "ingestion", "params": {"resource_ids": ["doc1", "doc2"]}}
    )
    assert isinstance(req, StartIngestionRequest)
    assert req.params.resource_ids == ["doc1", "doc2"]
