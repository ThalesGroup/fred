import asyncio

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from knowledge_flow_backend.features.content.content_service import ContentService


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _metadata(
    *,
    document_uid: str = "doc-1",
    file_name: str = "sample.docx",
    mime_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    preview_status: ProcessingStatus = ProcessingStatus.NOT_STARTED,
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(
            document_name=file_name,
            document_uid=document_uid,
            title="sample",
        ),
        source=SourceInfo(
            source_type=SourceType.PUSH,
            source_tag="uploads",
        ),
        file=FileInfo(
            mime_type=mime_type,
        ),
        processing=Processing(
            stages={
                ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE,
                ProcessingStage.PREVIEW_READY: preview_status,
            }
        ),
    )


class _MetadataStoreStub:
    def __init__(self, metadata: DocumentMetadata):
        self._metadata = metadata

    async def get_metadata_by_uid(self, document_uid: str, session=None) -> DocumentMetadata | None:
        if document_uid == self._metadata.document_uid:
            return self._metadata
        return None


class _ContentStoreStub:
    def __init__(self, payload: bytes | None = None):
        self.payload = payload or b""
        self.preview_calls: list[str] = []

    def get_preview_bytes(self, doc_path: str) -> bytes:
        self.preview_calls.append(doc_path)
        if self.payload:
            return self.payload
        raise FileNotFoundError(doc_path)


def test_get_markdown_preview_does_not_hit_store_when_preview_stage_not_ready(app_context):
    service = ContentService()
    metadata = _metadata(preview_status=ProcessingStatus.NOT_STARTED)
    content_store = _ContentStoreStub()
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store

    with pytest.raises(FileNotFoundError, match="Preview not ready for document doc-1"):
        asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert content_store.preview_calls == []


def test_get_markdown_preview_reads_output_when_preview_stage_is_done(app_context):
    service = ContentService()
    metadata = _metadata(preview_status=ProcessingStatus.DONE)
    content_store = _ContentStoreStub(payload=b"# Hello preview")
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store

    result = asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert result == "# Hello preview"
    assert content_store.preview_calls == ["doc-1/output/output.md"]
