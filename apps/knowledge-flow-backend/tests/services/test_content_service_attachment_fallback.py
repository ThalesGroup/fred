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

"""ContentService resolves both document sources agents can name.

`get_markdown_preview` is the single resolution point behind read_document,
summarize_document and extract_from_document: a corpus document (metadata +
preview artifact) or a session attachment (chat upload, vectors only). These
tests cover the routing between the two; the reconstruction itself lives on
`BaseVectorStore` and is covered by `tests/stores/test_base_vector_store.py`."""

from __future__ import annotations

import asyncio

import pytest
from fred_core import AuthorizationError, KeycloakUser
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
from fred_core.security.models import Resource

from knowledge_flow_backend.features.content.content_service import ContentService


def _user(uid: str = "u-1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username="tester", email="t@example.com", roles=["admin"])


def _metadata(document_uid: str, *, preview_status: ProcessingStatus) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name="sample.docx", document_uid=document_uid, title="sample"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        processing=Processing(
            stages={
                ProcessingStage.RAW_AVAILABLE: ProcessingStatus.DONE,
                ProcessingStage.PREVIEW_READY: preview_status,
            }
        ),
    )


class _RebacStub:
    """Fails closed on any uid it holds no tuple for - which is every session
    attachment, and is why the corpus lookup raises AuthorizationError rather
    than FileNotFoundError on Swift. `readable=None` models ReBAC disabled."""

    def __init__(self, readable: set[str] | None):
        self._readable = readable

    async def check_user_permission_or_raise(self, user, permission, resource_id: str) -> None:
        del permission
        if self._readable is not None and resource_id not in self._readable:
            raise AuthorizationError(user.uid, "read", Resource.DOCUMENTS)


class _MetadataStoreStub:
    def __init__(self, by_uid: dict[str, DocumentMetadata]):
        self._by_uid = by_uid

    async def get_metadata_by_uid(self, document_uid: str, session=None) -> DocumentMetadata | None:
        del session
        return self._by_uid.get(document_uid)


class _ContentStoreStub:
    def __init__(self, payload: bytes = b""):
        self._payload = payload
        self.preview_calls: list[str] = []

    def get_preview_bytes(self, doc_path: str) -> bytes:
        self.preview_calls.append(doc_path)
        if self._payload:
            return self._payload
        raise FileNotFoundError(doc_path)


class _VectorStoreStub:
    def __init__(self, text_by_uid: dict[str, str], *, error: Exception | None = None):
        self._text_by_uid = text_by_uid
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def get_own_session_document_text(self, document_uid: str, user_id: str) -> str:
        self.calls.append((document_uid, user_id))
        if self._error is not None:
            raise self._error
        return self._text_by_uid.get(document_uid, "")


def _service(
    app_context,
    *,
    corpus: dict[str, DocumentMetadata] | None = None,
    readable: set[str] | None = None,
    attachments: dict[str, str] | None = None,
    preview_payload: bytes = b"",
    vector_store_error: Exception | None = None,
) -> tuple[ContentService, _VectorStoreStub, _ContentStoreStub]:
    del app_context  # fixture only needed so ContentService() can build
    service = ContentService()
    service.metadata_store = _MetadataStoreStub(corpus or {})
    service.rebac = _RebacStub(readable)
    content_store = _ContentStoreStub(preview_payload)
    service.content_store = content_store
    vector_store = _VectorStoreStub(attachments or {}, error=vector_store_error)
    service._get_vector_store = lambda: vector_store
    return service, vector_store, content_store


def test_corpus_document_reads_its_preview_and_never_touches_the_vectors(app_context):
    service, vector_store, _ = _service(
        app_context,
        corpus={"doc-1": _metadata("doc-1", preview_status=ProcessingStatus.DONE)},
        readable={"doc-1"},
        preview_payload=b"# Corpus body",
    )

    assert asyncio.run(service.get_markdown_preview(_user(), "doc-1")) == "# Corpus body"
    assert vector_store.calls == []


def test_attachment_uid_falls_back_to_the_reconstructed_session_text(app_context):
    """No metadata record and no ReBAC tuple: the fallback is the only path."""
    service, vector_store, _ = _service(
        app_context,
        readable=set(),
        attachments={"att-1": "First page.\n\nSecond page."},
    )

    text = asyncio.run(service.get_markdown_preview(_user("u-1"), "att-1"))

    assert text == "First page.\n\nSecond page."
    assert vector_store.calls == [("att-1", "u-1")]


def test_denial_surfaces_when_nothing_is_reconstructable(app_context):
    """Someone else's attachment, an unknown uid, or a denied corpus document:
    the original 403 must reach the caller, never an empty document."""
    service, _, _ = _service(app_context, readable=set(), attachments={})

    with pytest.raises(AuthorizationError):
        asyncio.run(service.get_markdown_preview(_user(), "att-1"))


def test_rebac_disabled_path_still_falls_back_on_a_missing_metadata_record(app_context):
    """With ReBAC off the corpus miss is a plain FileNotFoundError; both the
    fallback and the surfaced 404 must keep working."""
    service, _, _ = _service(app_context, readable=None, attachments={"att-1": "Body."})

    assert asyncio.run(service.get_markdown_preview(_user(), "att-1")) == "Body."
    with pytest.raises(FileNotFoundError):
        asyncio.run(service.get_markdown_preview(_user(), "unknown"))


def test_a_broken_vector_store_does_not_rewrite_the_denial(app_context):
    """The fallback runs on an error path. If it blows up (unreachable store,
    missing credentials), the caller must still get its 403 - not a 400 or 500
    carrying an infrastructure message."""
    service, _, _ = _service(
        app_context,
        readable=set(),
        vector_store_error=ValueError("Missing OpenSearch credentials"),
    )

    with pytest.raises(AuthorizationError):
        asyncio.run(service.get_markdown_preview(_user(), "att-1"))


def test_corpus_document_with_an_unready_preview_does_not_scan_the_vectors(app_context):
    """The fallback is scoped to metadata resolution, not to any preview miss:
    a corpus document still ingesting must fail fast, not pay a chunk scan."""
    service, vector_store, content_store = _service(
        app_context,
        corpus={"doc-1": _metadata("doc-1", preview_status=ProcessingStatus.IN_PROGRESS)},
        readable={"doc-1"},
    )

    with pytest.raises(FileNotFoundError, match="Preview not ready for document doc-1"):
        asyncio.run(service.get_markdown_preview(_user(), "doc-1"))

    assert vector_store.calls == []
    assert content_store.preview_calls == []
