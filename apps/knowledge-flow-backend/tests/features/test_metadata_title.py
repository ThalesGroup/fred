import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.features.metadata.service import (
    InvalidMetadataRequest,
    MetadataNotFound,
    MetadataService,
)


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated metadata-service unit tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
    )


def _document(*, uid: str, name: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="application/pdf"),
        processing=Processing(),
    )


class _FakeRebac:
    async def check_user_permission_or_raise(self, user, permission, document_uid):
        del user, permission, document_uid


class _FakeMetadataStore:
    def __init__(self, doc: DocumentMetadata | None) -> None:
        self.doc = doc
        self.saved: DocumentMetadata | None = None

    async def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata | None:
        del document_uid
        return self.doc

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.saved = metadata


def _service(doc: DocumentMetadata | None) -> tuple[MetadataService, _FakeMetadataStore]:
    """Build one metadata service with stubbed collaborators, bypassing the real constructor."""

    service = object.__new__(MetadataService)
    store = _FakeMetadataStore(doc)
    service.metadata_store = store
    service.rebac = _FakeRebac()
    service.vector_store = None
    return service, store


@pytest.mark.asyncio
async def test_update_document_title_sets_title_and_modified_by():
    doc = _document(uid="doc-1", name="report.pdf")
    service, store = _service(doc)

    await service.update_document_title(_user(), "doc-1", "Q3 Report", "u-1")

    assert store.saved is not None
    assert store.saved.identity.title == "Q3 Report"
    assert store.saved.identity.last_modified_by == "u-1"
    # Cosmetic only (RFC decision 9): the ingested file name is untouched.
    assert store.saved.identity.document_name == "report.pdf"


@pytest.mark.asyncio
async def test_update_document_title_strips_whitespace():
    doc = _document(uid="doc-1", name="report.pdf")
    service, store = _service(doc)

    await service.update_document_title(_user(), "doc-1", "  Q3 Report  ", "u-1")

    assert store.saved.identity.title == "Q3 Report"


@pytest.mark.asyncio
async def test_update_document_title_rejects_blank_title():
    service, _store = _service(_document(uid="doc-1", name="report.pdf"))

    with pytest.raises(InvalidMetadataRequest):
        await service.update_document_title(_user(), "doc-1", "   ", "u-1")


@pytest.mark.asyncio
async def test_update_document_title_raises_when_document_missing():
    service, _store = _service(None)

    with pytest.raises(MetadataNotFound):
        await service.update_document_title(_user(), "doc-1", "New Title", "u-1")
