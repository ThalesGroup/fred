import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
)
from knowledge_flow_backend.features.filesystem.corpus_virtual_filesystem import (
    CorpusVirtualFilesystem,
)
from knowledge_flow_backend.features.tag.structure import Tag, TagType, TagWithItemsId


def _user() -> KeycloakUser:
    """Return one admin-like user for isolated filesystem unit tests."""

    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _document(*, uid: str, name: str, tag_ids: list[str]) -> DocumentMetadata:
    """
    Build one document metadata object with only the fields needed by corpus tests.

    Why this exists:
    - corpus filesystem tests should stay focused on path behavior, not metadata setup noise
    - one helper keeps document fixtures short and consistent

    How to use:
    - pass the stable uid, visible name, and tag ids for the document

    Example:
    - `_document(uid="doc-1", name="Report.pdf", tag_ids=["tag-1"])`
    """

    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="text/plain"),
        processing=Processing(),
        tags={"tag_ids": tag_ids, "tag_names": []},
    )


def _library(
    *,
    tag_id: str,
    name: str,
    path: str | None = None,
    item_ids: list[str] | None = None,
) -> TagWithItemsId:
    """
    Build one document-library tag fixture for corpus filesystem tests.

    Why this exists:
    - corpus tree behavior is driven by tag ids, names, and paths
    - one helper keeps tag fixtures readable across scenarios

    How to use:
    - pass the stable tag id, display name, optional folder path, and attached item ids

    Example:
    - `_library(tag_id="tag-1", name="Finance", path="Shared", item_ids=["doc-1"])`
    """

    return TagWithItemsId.from_tag(
        Tag(
            id=tag_id,
            created_at="2026-03-21T00:00:00Z",
            updated_at="2026-03-21T00:00:00Z",
            owner_id="u-1",
            name=name,
            path=path,
            description=None,
            type=TagType.DOCUMENT,
        ),
        item_ids=item_ids or [],
    )


class _TagServiceStub:
    def __init__(self, tags: list[TagWithItemsId]) -> None:
        self._by_id = {tag.id: tag for tag in tags}
        self._tags = tags

    async def list_all_tags_for_user(self, user, tag_type=None, limit=10000, offset=0):
        del user, tag_type, limit, offset
        return list(self._tags)

    async def get_tag_for_user(self, tag_id: str, user):
        del user
        return self._by_id[tag_id]


class _MetadataServiceStub:
    def __init__(self, docs: list[DocumentMetadata]) -> None:
        self._by_uid = {doc.document_uid: doc for doc in docs}
        self._docs = docs

    async def get_documents_metadata(self, user, filters_dict):
        del user, filters_dict
        return [doc.model_copy(deep=True) for doc in self._docs]

    async def get_document_metadata(self, user, document_uid: str):
        del user
        return self._by_uid[document_uid].model_copy(deep=True)

    async def get_document_metadata_in_tag(self, user, tag_id: str):
        del user
        return [doc.model_copy(deep=True) for doc in self._docs if tag_id in list(doc.tags.tag_ids or [])]


class _ContentServiceStub:
    async def get_markdown_preview(self, user, document_uid: str) -> str:
        del user
        return f"# Preview for {document_uid}"


class _FlakyContentServiceStub(_ContentServiceStub):
    def __init__(self, failing_ids: set[str]) -> None:
        self.failing_ids = failing_ids

    async def get_markdown_preview(self, user, document_uid: str) -> str:
        if document_uid in self.failing_ids:
            raise RuntimeError("preview unavailable")
        return await super().get_markdown_preview(user, document_uid)


def _corpus_filesystem(
    *,
    tags: list[TagWithItemsId],
    docs: list[DocumentMetadata],
    content_service: _ContentServiceStub | None = None,
) -> CorpusVirtualFilesystem:
    """
    Build one isolated corpus virtual filesystem for corpus unit tests.

    Why this exists:
    - corpus behavior should be tested at the module interface with explicit stubs
    - keeping construction in one helper avoids leaking service wiring into each test

    How to use:
    - pass stubbed tags, documents, and optionally a custom content service

    Example:
    - `_corpus_filesystem(tags=[library], docs=[document])`
    """

    return CorpusVirtualFilesystem(
        metadata_service=_MetadataServiceStub(docs),
        content_service=content_service or _ContentServiceStub(),
        tag_service=_TagServiceStub(tags),
    )


@pytest.mark.asyncio
async def test_list_legacy_documents_uses_readable_names(app_context):
    corpus_fs = _corpus_filesystem(
        tags=[],
        docs=[_document(uid="doc-1", name="Quarterly Report.pdf", tag_ids=[])],
    )

    entries = await corpus_fs.list_area(_user(), ("documents",))

    assert [entry.path for entry in entries] == ["Quarterly Report.pdf [doc-1]"]


@pytest.mark.asyncio
async def test_library_navigation_accepts_friendly_segments(app_context):
    library = _library(tag_id="tag-1", name="Finance", path="Shared", item_ids=["doc-1"])
    document = _document(uid="doc-1", name="Budget 2026.xlsx", tag_ids=["tag-1"])
    corpus_fs = _corpus_filesystem(tags=[library], docs=[document])

    library_entries = await corpus_fs.list_area(_user(), ("libraries",))
    document_entries = await corpus_fs.list_area(
        _user(),
        ("libraries", "Shared > Finance [tag-1]", "documents"),
    )
    preview = await corpus_fs.cat_area(
        _user(),
        (
            "libraries",
            "Shared > Finance [tag-1]",
            "documents",
            "Budget 2026.xlsx [doc-1]",
            "preview.md",
        ),
    )

    assert [entry.path for entry in library_entries] == ["Shared > Finance [tag-1]"]
    assert [entry.path for entry in document_entries] == ["Budget 2026.xlsx [doc-1]"]
    assert preview == "# Preview for doc-1"


@pytest.mark.asyncio
async def test_natural_tree_browsing_uses_library_folder_hierarchy(app_context):
    library = _library(tag_id="tag-1", name="TSN", path="CIR", item_ids=["doc-1"])
    document = _document(uid="doc-1", name="CIR_TSN_2024_BIDGPT.docx", tag_ids=["tag-1"])
    corpus_fs = _corpus_filesystem(tags=[library], docs=[document])

    root_entries = await corpus_fs.list_area(_user(), ())
    cir_entries = await corpus_fs.list_area(_user(), ("CIR",))
    tsn_entries = await corpus_fs.list_area(_user(), ("CIR", "TSN"))
    preview = await corpus_fs.cat_area(
        _user(),
        ("CIR", "TSN", "CIR_TSN_2024_BIDGPT.docx", "preview.md"),
    )

    assert [entry.path for entry in root_entries] == ["CIR"]
    assert [entry.path for entry in cir_entries] == ["TSN"]
    assert [entry.path for entry in tsn_entries] == ["CIR_TSN_2024_BIDGPT.docx"]
    assert preview == "# Preview for doc-1"


@pytest.mark.asyncio
async def test_grep_returns_natural_and_legacy_visible_paths(app_context):
    library = _library(tag_id="tag-1", name="Finance", path="Shared", item_ids=["doc-1"])
    document = _document(uid="doc-1", name="Budget 2026.xlsx", tag_ids=["tag-1"])
    corpus_fs = _corpus_filesystem(tags=[library], docs=[document])

    legacy_matches = await corpus_fs.grep_area(_user(), "Preview", ("documents",))
    natural_matches = await corpus_fs.grep_area(_user(), "Preview", ("Shared", "Finance"))

    assert legacy_matches == ["corpus/documents/Budget 2026.xlsx [doc-1]/preview.md"]
    assert natural_matches == ["corpus/Shared/Finance/Budget 2026.xlsx/preview.md"]


@pytest.mark.asyncio
async def test_list_area_uses_stable_suffix_when_document_name_collides_with_folder(app_context):
    library = _library(tag_id="tag-1", name="TSN", path="CIR", item_ids=[])
    document = _document(uid="doc-1", name="CIR", tag_ids=[])
    corpus_fs = _corpus_filesystem(tags=[library], docs=[document])

    entries = await corpus_fs.list_area(_user(), ())

    assert [entry.path for entry in entries] == ["CIR", "CIR [doc-1]"]


@pytest.mark.asyncio
async def test_stat_area_distinguishes_directory_and_file(app_context):
    library = _library(tag_id="tag-1", name="TSN", path="CIR", item_ids=["doc-1"])
    document = _document(uid="doc-1", name="Offer.docx", tag_ids=["tag-1"])
    corpus_fs = _corpus_filesystem(tags=[library], docs=[document])

    directory_stat = await corpus_fs.stat_area(_user(), ("CIR",))
    file_stat = await corpus_fs.stat_area(
        _user(),
        ("CIR", "TSN", "Offer.docx", "preview.md"),
    )

    assert directory_stat.is_dir()
    assert file_stat.is_file()
    assert file_stat.path == "CIR/TSN/Offer.docx/preview.md"


@pytest.mark.asyncio
async def test_grep_skips_preview_fetch_failures_when_searching_multiple_documents(app_context):
    library = _library(
        tag_id="tag-1",
        name="Finance",
        path="Shared",
        item_ids=["doc-1", "doc-2"],
    )
    first_document = _document(uid="doc-1", name="Budget.xlsx", tag_ids=["tag-1"])
    second_document = _document(uid="doc-2", name="Forecast.xlsx", tag_ids=["tag-1"])
    corpus_fs = _corpus_filesystem(
        tags=[library],
        docs=[first_document, second_document],
        content_service=_FlakyContentServiceStub({"doc-2"}),
    )

    matches = await corpus_fs.grep_area(_user(), "Preview", ("libraries",))

    assert matches == ["corpus/libraries/Shared > Finance [tag-1]/documents/Budget.xlsx [doc-1]/preview.md"]


@pytest.mark.asyncio
async def test_unknown_natural_folder_raises_file_not_found(app_context):
    corpus_fs = _corpus_filesystem(tags=[], docs=[])

    with pytest.raises(FileNotFoundError):
        await corpus_fs.cat_area(_user(), ("missing", "preview.md"))
