# Copyright Thales 2025
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

"""Tests for SummarizeService's uniform text resolution.

summarize_document must work for BOTH corpus documents (markdown preview) and
session attachments (chat uploads, which exist only as vectors). These tests
exercise the resolution + attachment-reconstruction logic directly, bypassing the
LLM summarizer."""

from __future__ import annotations

import pytest
from fred_core import AuthorizationError, KeycloakUser
from fred_core.security.models import Resource

from knowledge_flow_backend.features.summarize.service import SummarizeService


def _user(uid: str = "u-1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username="tester", email="t@example.com", roles=["admin"], groups=[])


class _ContentServiceStub:
    """Mimics corpus markdown preview: returns text for known uids, raises
    for everything else. On Swift the real failure for an unknown uid is
    AuthorizationError (the ReBAC check runs before the store lookup and fails
    closed), so that is the default; FileNotFoundError stays covered for the
    ReBAC-disabled path."""

    def __init__(self, by_uid: dict[str, str], *, error: type[Exception] = AuthorizationError) -> None:
        self._by_uid = by_uid
        self._error = error

    async def get_markdown_preview(self, user, document_uid: str) -> str:
        del user
        if document_uid not in self._by_uid:
            if self._error is AuthorizationError:
                raise AuthorizationError("u-1", "read", Resource.DOCUMENTS)
            raise self._error(f"No metadata found for document {document_uid}")
        return self._by_uid[document_uid]


class _VectorStoreStub:
    def __init__(self, chunks_by_uid: dict[str, list[dict]]) -> None:
        self._chunks_by_uid = chunks_by_uid

    def get_chunks_for_document(self, document_uid: str) -> list[dict]:
        return list(self._chunks_by_uid.get(document_uid, []))


class _ContextStub:
    def __init__(self, store: _VectorStoreStub) -> None:
        self._store = store

    def get_embedder(self):
        return object()

    def get_create_vector_store(self, _embedder):
        return self._store


def _service(
    *,
    corpus: dict[str, str],
    attachment_chunks: dict[str, list[dict]],
    corpus_error: type[Exception] = AuthorizationError,
) -> SummarizeService:
    service = SummarizeService.__new__(SummarizeService)  # bypass __init__ (no ApplicationContext)
    service.content_service = _ContentServiceStub(corpus, error=corpus_error)
    service.context = _ContextStub(_VectorStoreStub(attachment_chunks))
    return service


def _chunk(text: str, *, user_id: str, page: int | None = None, scope: str = "session") -> dict:
    md: dict = {"user_id": user_id, "document_uid": "att-1", "scope": scope}
    if page is not None:
        md["page"] = page
    return {"chunk_uid": f"c-{page}", "text": text, "metadata": md}


@pytest.mark.asyncio
async def test_corpus_document_uses_markdown_preview():
    service = _service(corpus={"doc-1": "Corpus body."}, attachment_chunks={})

    text = await service._get_document_markdown(_user(), "doc-1")

    assert text == "Corpus body."


@pytest.mark.asyncio
async def test_attachment_falls_back_to_reconstructed_vector_text():
    """No corpus record -> rebuild the text from the session vectors, in page order."""
    chunks = [
        _chunk("Second page.", user_id="u-1", page=2),
        _chunk("First page.", user_id="u-1", page=1),
    ]
    service = _service(corpus={}, attachment_chunks={"att-1": chunks})

    text = await service._get_document_markdown(_user("u-1"), "att-1")

    assert text == "First page.\n\nSecond page."


@pytest.mark.asyncio
async def test_attachment_of_another_user_surfaces_the_original_denial():
    """Attachments have no metadata-ReBAC record; the vectors' user_id is the gate.
    A uid owned by someone else must not be summarizable -> the original corpus
    denial (403 on Swift) surfaces, never someone else's text."""
    chunks = [_chunk("Secret.", user_id="other-user", page=1)]
    service = _service(corpus={}, attachment_chunks={"att-1": chunks})

    with pytest.raises(AuthorizationError):
        await service._get_document_markdown(_user("u-1"), "att-1")


@pytest.mark.asyncio
async def test_unknown_uid_surfaces_the_original_denial():
    service = _service(corpus={}, attachment_chunks={})

    with pytest.raises(AuthorizationError):
        await service._get_document_markdown(_user(), "does-not-exist")


@pytest.mark.asyncio
async def test_rebac_denied_corpus_document_not_reconstructable_from_its_vectors():
    """A corpus document the user is DENIED on may still have vector chunks
    carrying their user_id (e.g. they uploaded it before losing access). The
    fallback must not become a ReBAC bypass: corpus chunks (scope != session)
    are never joined, so the original 403 surfaces."""
    chunks = [_chunk("Corpus secret.", user_id="u-1", page=1, scope="library")]
    service = _service(corpus={}, attachment_chunks={"att-1": chunks})

    with pytest.raises(AuthorizationError):
        await service._get_document_markdown(_user("u-1"), "att-1")


@pytest.mark.asyncio
async def test_rebac_disabled_path_still_falls_back_on_404():
    """With ReBAC disabled the corpus miss is a plain FileNotFoundError — the
    attachment fallback and the surfaced 404 must both keep working."""
    chunks = [_chunk("Body.", user_id="u-1", page=1)]
    service = _service(corpus={}, attachment_chunks={"att-1": chunks}, corpus_error=FileNotFoundError)

    assert await service._get_document_markdown(_user("u-1"), "att-1") == "Body."
    with pytest.raises(FileNotFoundError):
        await service._get_document_markdown(_user("u-1"), "unknown")


@pytest.mark.asyncio
async def test_chunks_without_page_metadata_still_reconstruct():
    """Single combined-doc fallback ingests have no 'page'; must not crash on sort."""
    chunks = [_chunk("Whole doc.", user_id="u-1", page=None)]
    service = _service(corpus={}, attachment_chunks={"att-1": chunks})

    text = await service._get_document_markdown(_user("u-1"), "att-1")

    assert text == "Whole doc."
