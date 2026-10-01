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

"""Overwriting a document the user chose to replace.

The contract these pin: the replaced document keeps its identity, so anything
already pointing at it keeps resolving and now resolves to the new content;
its index goes before the new content lands, never after; and the storage
quota moves by the difference between the two files, not by the new file's
size.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.metadata.service import MetadataService

_T = datetime(2026, 1, 1, tzinfo=timezone.utc)
DESTINATION = "folder-a"
EXISTING_UID = "uid-report"
USER = KeycloakUser(uid="alice", username="alice", email=None, roles=[])


async def _returns_false(self, *args, **kwargs) -> bool:
    """A conditional write that lost its row — see the fence in adopt_existing_document."""
    return False


def _doc(uid: str, name: str, *, size: int, vectorized: bool = False) -> DocumentMetadata:
    metadata = DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=name, author="a", created=_T, modified=_T, last_modified_by="a"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
        file=FileInfo(file_type=FileType.OTHER, file_name=name, file_size_bytes=size),
        tags=Tagging(tag_ids=[DESTINATION]),
    )
    if vectorized:
        metadata.processing.stages[ProcessingStage.VECTORIZED] = ProcessingStatus.DONE
    return metadata


def _write_content(content_store, document_uid: str, name: str, body: bytes, tmp_path) -> None:
    input_dir = tmp_path / document_uid / name
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / name).write_bytes(body)
    content_store.save_input(document_uid, input_dir)


@pytest_asyncio.fixture
async def existing(app_context, metadata_store, content_store, tmp_path):
    """A 2 MB, already-vectorized "report.pdf" with its content in place."""
    previous = _doc(EXISTING_UID, "report.pdf", size=2_000_000, vectorized=True)
    await metadata_store.save_metadata(previous)
    _write_content(content_store, EXISTING_UID, "report.pdf", b"the old report", tmp_path)
    return previous


@pytest.mark.asyncio
async def test_the_replacement_becomes_the_existing_document(existing) -> None:
    fresh = _doc("uid-freshly-generated", "report.pdf", size=3_000_000)

    adopted = await get_ingestion_service().adopt_existing_document(USER, fresh, EXISTING_UID)

    assert adopted.document_uid == EXISTING_UID
    # A fresh extraction has produced nothing yet; carrying the replaced
    # document's stages would report it as indexed while it is not.
    assert adopted.processing.stages == {}


@pytest.mark.asyncio
async def test_the_document_keeps_every_library_it_was_in(app_context, metadata_store, content_store, tmp_path) -> None:
    # Replacing content is not moving the document. Keeping only the importing
    # folder's tag would remove it from the others — quota and access with it.
    shared = _doc(EXISTING_UID, "report.pdf", size=2_000_000)
    shared.tags.tag_ids = [DESTINATION, "folder-elsewhere"]
    await metadata_store.save_metadata(shared)
    _write_content(content_store, EXISTING_UID, "report.pdf", b"the old report", tmp_path)

    adopted = await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)

    assert sorted(adopted.tags.tag_ids) == sorted([DESTINATION, "folder-elsewhere"])


@pytest.mark.asyncio
async def test_the_row_stops_claiming_an_index_before_the_index_goes(existing, metadata_store, monkeypatch) -> None:
    # An interrupted replacement must not leave a document advertising vectors
    # it no longer has: unsearchable, with nothing saying so. The row is marked
    # unprocessed first, so whatever fails next, the row tells the truth.
    seen: list[dict] = []

    async def _record(self, document_uid, *, metadata=None, include_content=True):
        row = await metadata_store.get_metadata_by_uid(document_uid)
        seen.append({"stages_at_purge": dict(row.processing.stages)})

    monkeypatch.setattr(MetadataService, "purge_document_artifacts", _record)

    await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)

    assert seen == [{"stages_at_purge": {}}]


@pytest.mark.asyncio
async def test_a_document_deleted_meanwhile_is_not_purged(existing, metadata_store, monkeypatch) -> None:
    # The conditional update is the fence: if the row went while the import was
    # in flight, nothing of that document is ours to delete any more.
    purged: list[str] = []
    monkeypatch.setattr(MetadataService, "purge_document_artifacts", lambda *a, **k: purged.append("called"))
    await metadata_store.delete_metadata(EXISTING_UID)

    adopted = await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)

    assert purged == []
    assert adopted.document_uid == "uid-freshly-generated"


@pytest.mark.asyncio
async def test_a_document_deleted_during_the_fence_is_not_impersonated(existing, monkeypatch) -> None:
    # The row survived the read and went before the conditional write. Taking
    # its uid and its libraries anyway would have the caller save a row that
    # resurrects the deleted document — back into every library it was in,
    # including ones this import never targeted.
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    monkeypatch.setattr(IngestionService, "persist_progress", _returns_false)
    fresh = _doc("uid-freshly-generated", "report.pdf", size=3_000_000)

    adopted = await get_ingestion_service().adopt_existing_document(USER, fresh, EXISTING_UID)

    assert adopted.document_uid == "uid-freshly-generated"
    assert adopted.tags.tag_ids == [DESTINATION]


@pytest.mark.asyncio
async def test_the_replaced_document_stops_answering_with_its_old_content(existing, monkeypatch) -> None:
    # The whole point of replacing: the old chunks must not survive under the
    # uid the new content is about to be indexed under, or the document answers
    # out of both at once. Runs the real purge — the other tests replace it, so
    # none of them can see whether it does anything.
    deleted: list[str] = []

    class _Spy:
        def delete_vectors_for_document(self, document_uid: str) -> None:
            deleted.append(document_uid)

    monkeypatch.setattr(MetadataService, "_vector_store", lambda self: _Spy())

    await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)

    assert deleted == [EXISTING_UID]


@pytest.mark.asyncio
async def test_the_index_goes_but_the_content_stays_until_it_is_replaced(existing, monkeypatch) -> None:
    # The interrupted overwrite must never leave the old index answering for
    # new content. Dropping the index first and the bytes only when the new
    # ones are written is what guarantees it: an interruption leaves the
    # document unindexed, never wrongly indexed.
    purged: list[dict] = []

    async def _record(self, document_uid, *, metadata=None, include_content=True):
        purged.append({"uid": document_uid, "include_content": include_content})

    monkeypatch.setattr(MetadataService, "purge_document_artifacts", _record)

    await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)

    assert purged == [{"uid": EXISTING_UID, "include_content": False}]


@pytest.mark.asyncio
async def test_purging_without_the_content_really_leaves_it_readable(existing, content_store) -> None:
    await MetadataService().purge_document_artifacts(EXISTING_UID, metadata=existing, include_content=False)

    assert content_store.get_content(EXISTING_UID).read() == b"the old report"


@pytest.mark.asyncio
async def test_a_reference_to_the_document_resolves_to_the_new_content(existing, content_store, tmp_path) -> None:
    # Whatever already cites this document cites its uid. Preserving the uid
    # is what keeps that citation resolving — now to what replaced it.
    await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)
    _write_content(content_store, EXISTING_UID, "report.pdf", b"the new report", tmp_path / "new")

    assert content_store.get_content(EXISTING_UID).read() == b"the new report"


@pytest.mark.asyncio
async def test_the_quota_moves_by_the_difference_not_the_whole_file(existing, monkeypatch) -> None:
    charged: list[dict] = []

    async def _record(self, *, old_size, new_size, old_tags, new_tags, user_id):
        charged.append({"old_size": old_size, "new_size": new_size})

    monkeypatch.setattr(MetadataService, "_adjust_team_storage", _record)

    service = MetadataService()
    adopted = await get_ingestion_service().adopt_existing_document(USER, _doc("uid-freshly-generated", "report.pdf", size=3_000_000), EXISTING_UID)
    await service._persist_metadata_and_follow_up(USER, adopted)

    # 2 MB replaced by 3 MB is 1 MB more, not 3 MB more — across every write
    # the replacement makes, marking the row unprocessed included.
    assert sum(call["new_size"] - call["old_size"] for call in charged) == 1_000_000
