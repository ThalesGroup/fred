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

import asyncio
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.core.stores.content.base_content_store import FileMetadata
from knowledge_flow_backend.features.content.content_service import ContentService


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
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
    def __init__(self, payload: bytes | None = None, *, stored_file_name: str = "original_upload.docx"):
        self.payload = payload or b""
        self.preview_calls: list[str] = []
        self.stored_file_name = stored_file_name

    def get_output_artifact(self, doc_path: str) -> bytes:
        self.preview_calls.append(doc_path)
        if self.payload:
            return self.payload
        raise FileNotFoundError(doc_path)

    def get_file_metadata(self, document_uid: str) -> FileMetadata:
        del document_uid
        # Deliberately different from the DB's identity.document_name — this is
        # the blob's own stored name, which never changes on a rename.
        return FileMetadata(size=1234, file_name=self.stored_file_name, content_type=None)


class _TabularPreviewServiceStub:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls: list[tuple[str, int]] = []

    async def read_dataset_preview_frame_trusted(self, metadata, *, max_rows: int = 200):
        document_uid = metadata.document_uid
        self.calls.append((document_uid, max_rows))
        return self.frame


def test_get_markdown_preview_does_not_hit_store_when_preview_stage_not_ready(app_context):
    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(preview_status=ProcessingStatus.NOT_STARTED)
    content_store = _ContentStoreStub()
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store

    with pytest.raises(FileNotFoundError, match="Preview not ready for document doc-1"):
        asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert content_store.preview_calls == []


def test_get_markdown_preview_reads_output_when_preview_stage_is_done(app_context):
    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(preview_status=ProcessingStatus.DONE)
    content_store = _ContentStoreStub(payload=b"# Hello preview")
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store

    result = asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert result == "# Hello preview"
    assert content_store.preview_calls == ["doc-1/output/output.md"]


def test_get_markdown_preview_reads_csv_from_tabular_artifact_without_table_csv(app_context):
    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(
        file_name="sales.csv",
        mime_type="text/csv",
        preview_status=ProcessingStatus.NOT_STARTED,
    )
    metadata.processing.stages[ProcessingStage.SQL_INDEXED] = ProcessingStatus.DONE
    metadata.extensions = {
        "tabular_v1": {
            "dataset_uid": "doc-1",
            "object_key": "tabular/datasets/doc-1/rev/data.parquet",
            "source_revision": "rev",
            "format": "parquet",
            "row_count": 2,
            "columns": [],
            "generated_at": "2026-04-13T10:00:00+00:00",
            "file_size_bytes": 128,
        }
    }
    content_store = _ContentStoreStub()
    preview_service = _TabularPreviewServiceStub(
        pd.DataFrame(
            [
                {"city": "Paris", "amount": 10},
                {"city": "Lyon", "amount": 20},
            ]
        )
    )
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store
    service._tabular_service = preview_service

    result = asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert "| city" in result
    assert "| Paris" in result
    assert content_store.preview_calls == []
    assert preview_service.calls == [("doc-1", 200)]


def test_get_markdown_preview_escapes_pipe_characters_from_tabular_artifact(app_context):
    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(
        file_name="sales.csv",
        mime_type="text/csv",
        preview_status=ProcessingStatus.NOT_STARTED,
    )
    metadata.processing.stages[ProcessingStage.SQL_INDEXED] = ProcessingStatus.DONE
    metadata.extensions = {
        "tabular_v1": {
            "dataset_uid": "doc-1",
            "object_key": "tabular/datasets/doc-1/rev/data.parquet",
            "source_revision": "rev",
            "format": "parquet",
            "row_count": 1,
            "columns": [],
            "generated_at": "2026-04-13T10:00:00+00:00",
            "file_size_bytes": 128,
        }
    }
    content_store = _ContentStoreStub()
    preview_service = _TabularPreviewServiceStub(pd.DataFrame([{"tags_csv": "alpha|beta|release"}]))
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store
    service._tabular_service = preview_service

    result = asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert "alpha&#124;beta&#124;release" in result
    assert content_store.preview_calls == []
    assert preview_service.calls == [("doc-1", 200)]


def test_get_file_metadata_uses_db_document_name_not_stored_blob_name(app_context):
    # Regression test for the rename "blind spot": get_file_metadata used to
    # read file_name straight from the content store's own stored blob name,
    # which never changes on a rename, instead of the DB record — so the
    # in-app preview/stream endpoint kept showing the old name forever.
    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(file_name="Q3-Final.pdf")
    content_store = _ContentStoreStub(stored_file_name="report_v1.pdf")
    service.metadata_store = _MetadataStoreStub(metadata)
    service.content_store = content_store

    result = asyncio.run(service.get_file_metadata_trusted(metadata))

    assert result.file_name == "Q3-Final.pdf"


@pytest.mark.parametrize("range_header,expected,status", [(None, b"abcdef", 200), ("bytes=1-3", b"bcd", 206)])
def test_stream_authorizes_once_before_headers_and_bytes(app_context, range_header, expected, status):
    from io import BytesIO

    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from fred_core import get_current_user

    from knowledge_flow_backend.features.content.content_controller import ContentController

    service = ContentService()
    service.corpus_access = AsyncMock()
    metadata = _metadata(file_name="renamed.pdf")
    service.metadata_store = _MetadataStoreStub(metadata)

    class Store:
        def get_file_metadata(self, uid):
            return FileMetadata(size=6, file_name="original.pdf", content_type="application/pdf")

        def get_content(self, uid):
            return BytesIO(b"abcdef")

        def get_content_range(self, uid, *, start, length):
            return BytesIO(b"abcdef"[start : start + length])

    service.content_store = Store()
    controller = ContentController.__new__(ContentController)
    controller.service = service
    router = APIRouter()
    controller._register_routes(router)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    response = TestClient(app).get("/raw_content/stream/doc-1", headers={"Range": range_header} if range_header else {})
    assert response.status_code == status
    assert response.content == expected
    assert "renamed.pdf" in response.headers["content-disposition"]
    service.corpus_access.check_document.assert_awaited_once_with(_user(), metadata)
