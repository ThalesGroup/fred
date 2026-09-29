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

"""What an import does with a name the destination folder already holds.

`_plan_import` decides it once, before anything is written; `_plan_events` and
`_files_to_import` turn that decision into what the client sees and what the
import actually touches. These pin the decision itself — an undecided conflict
is never resolved on the user's behalf, a skip is not a failure, and an
overwrite names the document it replaces.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.common.structures import Status
from knowledge_flow_backend.features.ingestion.ingestion_controller import (
    EMPTY_IMPORT_PLAN,
    ImportConflictDecision,
    ImportPlan,
    IngestionController,
    _plan_import,
)

_T = datetime(2026, 1, 1, tzinfo=timezone.utc)
DESTINATION = "folder-a"


def _doc(uid: str, name: str, tag_id: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=name, author="a", created=_T, modified=_T, last_modified_by="a"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
        file=FileInfo(file_type=FileType.OTHER, file_name=name),
        tags=Tagging(tag_ids=[tag_id]),
    )


@pytest_asyncio.fixture
async def store(app_context, metadata_store):
    await metadata_store.save_metadata(_doc("uid-report", "report.pdf", DESTINATION))
    await metadata_store.save_metadata(_doc("uid-notes", "notes.md", DESTINATION))
    await metadata_store.save_metadata(_doc("uid-elsewhere", "report.pdf", "folder-b"))
    return metadata_store


@pytest.mark.asyncio
async def test_a_conflict_without_a_decision_is_left_undecided(store) -> None:
    plan = await _plan_import(["report.pdf", "fresh.pdf"], [DESTINATION], {})

    assert plan.undecided == ["report.pdf"]
    assert plan.overwrite_uid == {}
    assert plan.skipped == []


@pytest.mark.asyncio
async def test_skip_keeps_the_existing_document(store) -> None:
    plan = await _plan_import(["report.pdf"], [DESTINATION], {"report.pdf": ImportConflictDecision.SKIP})

    assert plan.skipped == ["report.pdf"]
    assert plan.overwrite_uid == {}


@pytest.mark.asyncio
async def test_overwrite_names_the_document_it_replaces(store) -> None:
    plan = await _plan_import(["report.pdf"], [DESTINATION], {"report.pdf": ImportConflictDecision.OVERWRITE})

    assert plan.overwrite_uid == {"report.pdf": "uid-report"}
    assert plan.undecided == []


@pytest.mark.asyncio
async def test_a_name_held_only_elsewhere_is_not_a_conflict(store) -> None:
    # "report.pdf" also exists in folder-b; importing into folder-a must not
    # ask about it, and must not overwrite the other folder's document.
    plan = await _plan_import(["report.pdf"], ["folder-b"], {})
    assert plan.undecided == ["report.pdf"]

    plan = await _plan_import(["notes.md"], ["folder-b"], {})
    assert plan == EMPTY_IMPORT_PLAN


@pytest.mark.asyncio
async def test_a_name_held_twice_cannot_be_overwritten(store) -> None:
    # An alternate version leaves two documents sharing a display name, so
    # "the existing document" names neither. Refused rather than guessed.
    await store.save_metadata(_doc("uid-report-v1", "report.pdf", DESTINATION))

    plan = await _plan_import(["report.pdf"], [DESTINATION], {"report.pdf": ImportConflictDecision.OVERWRITE})

    assert plan.ambiguous == ["report.pdf"]
    assert plan.overwrite_uid == {}


@pytest.mark.asyncio
async def test_a_destinationless_import_asks_nothing(store) -> None:
    # No folder, no folder to conflict with.
    assert await _plan_import(["report.pdf"], [], {}) == EMPTY_IMPORT_PLAN


@pytest.mark.asyncio
async def test_a_decision_for_a_name_that_does_not_conflict_is_inert(store) -> None:
    plan = await _plan_import(["fresh.pdf"], [DESTINATION], {"fresh.pdf": ImportConflictDecision.OVERWRITE})

    assert plan == EMPTY_IMPORT_PLAN


def test_a_skip_is_reported_as_kept_and_a_late_conflict_as_a_conflict() -> None:
    plan = ImportPlan(overwrite_uid={}, skipped=["kept.pdf"], undecided=["taken.pdf"], ambiguous=["twice.pdf"])

    events = [json.loads(line) for line in IngestionController._plan_events(plan)]

    by_name = {event["filename"]: event for event in events}
    assert by_name["kept.pdf"]["status"] == Status.IGNORED.value
    assert by_name["taken.pdf"]["status"] == Status.CONFLICT.value
    assert "taken.pdf" in by_name["taken.pdf"]["error"]
    # Only a folder holding the name twice is a genuine failure: the user
    # cannot answer it, something has to be cleaned up first.
    assert by_name["twice.pdf"]["status"] == Status.FAILED.value


def test_excluded_files_are_dropped_and_their_temporary_copies_released(tmp_path) -> None:
    # `uploadfile_to_path` nests each upload two levels deep in its own
    # workdir, and the cleanup removes that workdir — mirror the layout.
    def _upload(name: str) -> pathlib.Path:
        path = tmp_path / name / "input" / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")
        return path

    kept_file = _upload("kept.pdf")
    excluded_file = _upload("taken.pdf")

    plan = ImportPlan(overwrite_uid={}, skipped=[], undecided=["taken.pdf"], ambiguous=[])
    remaining = IngestionController._files_to_import([("kept.pdf", kept_file), ("taken.pdf", excluded_file)], plan)

    assert remaining == [("kept.pdf", kept_file)]
    assert not excluded_file.exists()
    assert kept_file.exists()
