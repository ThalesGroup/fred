import pytest
from fred_core import FileTypeBucket, KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.features.tag.tag_service import TagService


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated tag-service unit tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
    )


def _document(*, uid: str, name: str, size_bytes: int, tag_ids: list[str]) -> DocumentMetadata:
    """Build one document metadata object with only the fields the stats aggregate reads."""

    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="application/octet-stream", file_size_bytes=size_bytes),
        processing=Processing(),
        tags={"tag_ids": tag_ids, "tag_names": []},
    )


class _FakeMetadataService:
    def __init__(self, docs_by_tag: dict[str, list[DocumentMetadata]]) -> None:
        self._docs_by_tag = docs_by_tag
        self.calls: list[str] = []

    async def get_document_metadata_in_tag(self, user, tag_id: str) -> list[DocumentMetadata]:
        del user
        self.calls.append(tag_id)
        return self._docs_by_tag.get(tag_id, [])


def _service(docs_by_tag: dict[str, list[DocumentMetadata]], tag_ids: set[str]) -> TagService:
    """Build one tag service with stubbed collaborators, bypassing the real constructor."""

    service = object.__new__(TagService)

    async def _list_authorized_tags_ids(user, owner_filter, team_id):
        del user, owner_filter, team_id
        return tag_ids

    service.list_authorized_tags_ids = _list_authorized_tags_ids
    service.document_metadata_service = _FakeMetadataService(docs_by_tag)
    return service


@pytest.mark.asyncio
async def test_get_corpus_type_stats_buckets_and_sums_by_type():
    docs_by_tag = {
        "lib-1": [
            _document(uid="doc-1", name="report.pdf", size_bytes=100, tag_ids=["lib-1"]),
            _document(uid="doc-2", name="deck.pptx", size_bytes=200, tag_ids=["lib-1"]),
        ],
        "lib-2": [
            _document(uid="doc-3", name="sheet.xlsx", size_bytes=50, tag_ids=["lib-2"]),
        ],
    }
    service = _service(docs_by_tag, tag_ids={"lib-1", "lib-2"})

    stats = await service.get_corpus_type_stats(_user(), "team-1")

    assert stats[FileTypeBucket.PDF] == (1, 100)
    assert stats[FileTypeBucket.PPT] == (1, 200)
    assert stats[FileTypeBucket.EXCEL] == (1, 50)


@pytest.mark.asyncio
async def test_get_corpus_type_stats_dedupes_documents_shared_across_libraries():
    shared_doc = _document(uid="doc-1", name="report.pdf", size_bytes=100, tag_ids=["lib-1", "lib-2"])
    docs_by_tag = {"lib-1": [shared_doc], "lib-2": [shared_doc]}
    service = _service(docs_by_tag, tag_ids={"lib-1", "lib-2"})

    stats = await service.get_corpus_type_stats(_user(), "team-1")

    assert stats[FileTypeBucket.PDF] == (1, 100)


@pytest.mark.asyncio
async def test_get_corpus_type_stats_returns_empty_for_team_with_no_libraries():
    service = _service({}, tag_ids=set())

    stats = await service.get_corpus_type_stats(_user(), "team-1")

    assert stats == {}
