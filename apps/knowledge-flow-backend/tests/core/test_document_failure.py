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

"""#2279 — a Temporal-issued timeout must reach the document, not just the task."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from fred_core.tasks.models import TaskState

from knowledge_flow_backend.features.scheduler import document_failure
from knowledge_flow_backend.features.scheduler.document_failure import (
    mark_in_progress_stages_failed,
    on_reconciled_terminal,
)


def _doc(uid: str, stages: dict[ProcessingStage, ProcessingStatus]) -> DocumentMetadata:
    metadata = DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="tag-1", pull_location=None),
    )
    metadata.processing.stages = dict(stages)
    return metadata


class _StubStore:
    def __init__(self, metadata: DocumentMetadata | None) -> None:
        self._metadata = metadata
        self.saved: list[DocumentMetadata] = []

    async def get_metadata_by_uid(self, document_uid: str):
        return self._metadata

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.saved.append(metadata)


@pytest.fixture
def store(monkeypatch):
    """Swap the metadata store the helper resolves through ApplicationContext."""

    def _install(metadata: DocumentMetadata | None) -> _StubStore:
        stub = _StubStore(metadata)
        monkeypatch.setattr(document_failure, "_resolve_store", lambda: stub)
        return stub

    return _install


@pytest.mark.asyncio
async def test_marks_in_progress_stages_failed(store):
    stub = store(
        _doc(
            "doc-1",
            {
                ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE,
                ProcessingStage.VECTORIZED: ProcessingStatus.IN_PROGRESS,
            },
        )
    )

    assert await mark_in_progress_stages_failed("doc-1", "Execution timed_out") is True

    saved = stub.saved[0]
    assert saved.processing.stages[ProcessingStage.VECTORIZED] == ProcessingStatus.FAILED
    assert saved.processing.errors[ProcessingStage.VECTORIZED] == "Execution timed_out"
    # A stage that already completed is never rewritten.
    assert saved.processing.stages[ProcessingStage.RAW_AVAILABLE] == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_leaves_document_untouched_when_no_stage_in_progress(store):
    # The activity's own `except` already recorded a precise error, or the work
    # finished. Rewriting here would clobber the better message.
    stub = store(
        _doc(
            "doc-1",
            {
                ProcessingStage.VECTORIZED: ProcessingStatus.FAILED,
                ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE,
            },
        )
    )

    assert await mark_in_progress_stages_failed("doc-1", "Execution timed_out") is False
    assert stub.saved == []


@pytest.mark.asyncio
async def test_missing_document_is_not_an_error(store):
    stub = store(None)

    assert await mark_in_progress_stages_failed("gone", "Execution timed_out") is False
    assert stub.saved == []


@pytest.mark.asyncio
async def test_store_failure_is_swallowed(monkeypatch):
    # The caller is always already on a failure path — a metadata write must
    # never be the reason that failure goes unreported.
    def _boom():
        raise RuntimeError("postgres down")

    monkeypatch.setattr(document_failure, "_resolve_store", _boom)

    assert await mark_in_progress_stages_failed("doc-1", "Execution timed_out") is False


# ── the reconciliation hook itself ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_hook_fails_stages_for_document_target(monkeypatch):
    seen: list[tuple[str, str]] = []

    async def _spy(document_uid: str, message: str) -> bool:
        seen.append((document_uid, message))
        return True

    monkeypatch.setattr(document_failure, "mark_in_progress_stages_failed", _spy)
    run = SimpleNamespace(target={"type": "document", "id": "doc-1", "label": "d"})

    await on_reconciled_terminal(run, TaskState.failed, "Execution timed_out")

    assert seen == [("doc-1", "Execution timed_out")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,target",
    [
        # A user-requested cancellation is not an error — reconciliation keeps it
        # out of failure counts, so the document must not go red either.
        (TaskState.cancelled, {"type": "document", "id": "doc-1"}),
        # Non-document targets (erasure on a user, migration on a database) have
        # no processing stages to repair.
        (TaskState.failed, {"type": "user", "id": "u-1"}),
        (TaskState.failed, None),
        (TaskState.failed, {"type": "document"}),
    ],
)
async def test_hook_is_a_noop(monkeypatch, state, target):
    called: list[str] = []

    async def _spy(document_uid: str, message: str) -> bool:
        called.append(document_uid)
        return True

    monkeypatch.setattr(document_failure, "mark_in_progress_stages_failed", _spy)

    await on_reconciled_terminal(SimpleNamespace(target=target), state, "msg")

    assert called == []
