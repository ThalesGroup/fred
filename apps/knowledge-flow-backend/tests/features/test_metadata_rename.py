import pytest
from fred_core import KeycloakUser, RebacDisabledResult
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.features.metadata.service import (
    DocumentNameCollisionError,
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


def _document(*, uid: str, name: str, tag_ids: list[str] | None = None, vectorized: bool = False) -> DocumentMetadata:
    stages = {ProcessingStage.VECTORIZED: ProcessingStatus.DONE} if vectorized else {}
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="application/pdf"),
        processing=Processing(stages=stages),
        tags=Tagging(tag_ids=tag_ids or []),
    )


class _FakeRebac:
    async def check_user_permission_or_raise(self, user, permission, document_uid):
        del user, permission, document_uid

    async def lookup_user_resources(self, user, permission):
        del user, permission
        return RebacDisabledResult()


class _FakeMetadataStore:
    def __init__(self, doc: DocumentMetadata | None, siblings: list[DocumentMetadata] | None = None) -> None:
        self.doc = doc
        self.siblings = siblings or []
        self.saved: DocumentMetadata | None = None

    async def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata | None:
        del document_uid
        return self.doc

    async def get_metadata_in_tag(self, tag_id: str) -> list[DocumentMetadata]:
        del tag_id
        return self.siblings

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.saved = metadata


class _FakeVectorStore:
    def __init__(self, *, supported: bool = True) -> None:
        self.supported = supported
        self.calls: list[tuple[str, str]] = []

    def set_document_name(self, *, document_uid: str, document_name: str) -> None:
        if not self.supported:
            raise NotImplementedError("does not support renaming")
        self.calls.append((document_uid, document_name))


def _service(
    doc: DocumentMetadata | None,
    *,
    siblings: list[DocumentMetadata] | None = None,
    vector_store: _FakeVectorStore | None = None,
) -> tuple[MetadataService, _FakeMetadataStore]:
    """Build one metadata service with stubbed collaborators, bypassing the real constructor."""

    service = object.__new__(MetadataService)
    store = _FakeMetadataStore(doc, siblings)
    service.metadata_store = store
    service.rebac = _FakeRebac()
    service.vector_store = vector_store
    return service, store


@pytest.mark.asyncio
async def test_rename_document_updates_name_and_clears_title():
    doc = _document(uid="doc-1", name="report.pdf")
    doc.identity.title = "An old cosmetic title"
    service, store = _service(doc)

    result = await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert store.saved is not None
    assert store.saved.identity.document_name == "Q3-Final.pdf"
    # A real rename supersedes the cosmetic title stand-in — otherwise
    # documentDisplayName()'s "title || document_name" fallback would keep
    # showing the old name forever.
    assert store.saved.identity.title is None
    assert store.saved.identity.last_modified_by == "u-1"
    assert store.saved.identity.modified is not None
    assert result is store.saved


@pytest.mark.asyncio
async def test_rename_document_is_a_noop_when_name_is_unchanged():
    doc = _document(uid="doc-1", name="report.pdf")
    service, store = _service(doc)

    await service.rename_document(_user(), "doc-1", "report.pdf", "u-1")

    assert store.saved is None


@pytest.mark.asyncio
async def test_rename_document_rejects_extension_change():
    doc = _document(uid="doc-1", name="report.pdf")
    service, _store = _service(doc)

    with pytest.raises(InvalidMetadataRequest):
        await service.rename_document(_user(), "doc-1", "report.docx", "u-1")


@pytest.mark.asyncio
async def test_rename_document_rejects_blank_name():
    service, _store = _service(_document(uid="doc-1", name="report.pdf"))

    with pytest.raises(InvalidMetadataRequest):
        await service.rename_document(_user(), "doc-1", "   ", "u-1")


@pytest.mark.asyncio
async def test_rename_document_raises_when_document_missing():
    service, _store = _service(None)

    with pytest.raises(MetadataNotFound):
        await service.rename_document(_user(), "doc-1", "new.pdf", "u-1")


@pytest.mark.asyncio
async def test_rename_document_rejects_collision_with_tag_sibling():
    doc = _document(uid="doc-1", name="report.pdf", tag_ids=["tag-a"])
    sibling = _document(uid="doc-2", name="final.pdf", tag_ids=["tag-a"])
    service, store = _service(doc, siblings=[sibling])

    with pytest.raises(DocumentNameCollisionError):
        await service.rename_document(_user(), "doc-1", "final.pdf", "u-1")
    assert store.saved is None


@pytest.mark.asyncio
async def test_rename_document_allows_reusing_its_own_current_shape_as_a_sibling():
    # A sibling entry for the SAME document (e.g. a stale self-reference) must
    # never block a rename against itself.
    doc = _document(uid="doc-1", name="report.pdf", tag_ids=["tag-a"])
    service, store = _service(doc, siblings=[doc])

    await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert store.saved.identity.document_name == "Q3-Final.pdf"


@pytest.mark.asyncio
async def test_rename_document_syncs_vector_store_when_vectorized():
    doc = _document(uid="doc-1", name="report.pdf", vectorized=True)
    vector_store = _FakeVectorStore()
    service, _store = _service(doc, vector_store=vector_store)

    await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert vector_store.calls == [("doc-1", "Q3-Final.pdf")]


@pytest.mark.asyncio
async def test_rename_document_skips_vector_store_when_not_vectorized():
    doc = _document(uid="doc-1", name="report.pdf", vectorized=False)
    vector_store = _FakeVectorStore()
    service, _store = _service(doc, vector_store=vector_store)

    await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert vector_store.calls == []


@pytest.mark.asyncio
async def test_rename_document_succeeds_even_if_vector_store_does_not_support_it():
    doc = _document(uid="doc-1", name="report.pdf", vectorized=True)
    vector_store = _FakeVectorStore(supported=False)
    service, store = _service(doc, vector_store=vector_store)

    await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert store.saved.identity.document_name == "Q3-Final.pdf"


@pytest.mark.asyncio
async def test_rename_document_succeeds_even_if_vector_store_raises():
    doc = _document(uid="doc-1", name="report.pdf", vectorized=True)

    class _ExplodingVectorStore:
        def set_document_name(self, *, document_uid: str, document_name: str) -> None:
            raise RuntimeError("boom")

    service, store = _service(doc, vector_store=_ExplodingVectorStore())

    await service.rename_document(_user(), "doc-1", "Q3-Final.pdf", "u-1")

    assert store.saved.identity.document_name == "Q3-Final.pdf"
