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

"""
Test suite for VectorSearchService in vector_search_service.py.

Covers:
- Similarity search functionality with nominal, failure, and edge cases.
- Behavior when no question is given or k=0.
- Mocked vector store and embedder via DummyContext.
"""

from contextlib import contextmanager

import pytest
from fred_core import KeycloakUser
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import AnnHit
from knowledge_flow_backend.features.vector_search import vector_search_service
from knowledge_flow_backend.features.vector_search.vector_search_service import VectorSearchService
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchPolicyName

pytestmark = pytest.mark.asyncio


class DummyVectorStore:
    """
    Mock vector store that simulates similarity search with dummy results.
    Raises ValueError on empty question.
    """

    def ann_search(self, query, *, k=10, search_filter=None):
        if not query:
            raise ValueError("Question must not be empty")
        if k <= 0:
            return []
        docs = [
            AnnHit(
                document=Document(
                    page_content="answer 1",
                    metadata={
                        "document_uid": "doc-1",
                        "document_name": "doc1.md",
                        "retrievable": True,
                        "scope": "corpus",
                        "tag_ids": [],
                    },
                ),
                score=0.9,
            ),
            AnnHit(
                document=Document(
                    page_content="answer 2",
                    metadata={
                        "document_uid": "doc-2",
                        "document_name": "doc2.md",
                        "retrievable": True,
                        "scope": "corpus",
                        "tag_ids": [],
                    },
                ),
                score=0.8,
            ),
        ]
        return docs[: min(k, 2)]


class DummyKPI:
    @contextmanager
    def timer(self, *_args, **_kwargs):
        dims = {}
        yield dims

    def count(self, *_args, **_kwargs):
        return None

    def gauge(self, *_args, **_kwargs):
        return None


class DummyTag:
    def __init__(self, name="tag", full_path="/tag"):
        self.name = name
        self.full_path = full_path
        self.item_ids = []


class DummyTagService:
    def __init__(self):
        from types import SimpleNamespace

        self.corpus_access = SimpleNamespace(folders=self)

    async def get_tags_by_ids(self, folder_ids):
        from types import SimpleNamespace

        return [SimpleNamespace(id=folder_id, name="tag", full_path="tag") for folder_id in folder_ids]

    async def list_authorized_tags_ids(self, _user, _owner_filter=None, _team_id=None):
        # Non-empty authorized scope so corpus search path is exercised in unit tests.
        return {"tag-1"}

    async def get_tag_for_user(self, _tag_id, _user):
        return DummyTag()


class DummyMetadataService:
    def __init__(self):
        self.metadata_store = self

    async def get_metadata_by_uids(self, document_uids):
        from types import SimpleNamespace

        return [SimpleNamespace(document_uid=uid, kind="corpus", tags=SimpleNamespace(tag_ids=["foreign-tag" if uid == "foreign" else "tag-1"])) for uid in document_uids]


class DummyContext:
    """
    Mock application context that returns dummy embedder and vector store.
    """

    def get_embedder(self):
        return "dummy_embedder"

    def get_create_vector_store(self, embedder):
        return DummyVectorStore()

    def get_crossencoder_model(self):
        return None

    def get_kpi_writer(self):
        return DummyKPI()


@pytest.fixture
def test_user():
    return KeycloakUser(uid="test-user", username="testuser", email="testuser@localhost", roles=["admin"])


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


async def test_similarity_search_success(monkeypatch, test_user):
    """Test: performs similarity search with a valid question and k=2.
    Asserts returned objects are Document-score tuples."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    results = await vector_svc.search(
        question="What is AI?",
        user=test_user,
        top_k=2,
        document_library_tags_ids=None,
        policy_name=SearchPolicyName.semantic,
    )
    assert isinstance(results, list)
    assert all(getattr(hit, "content", None) for hit in results)
    assert len(results) == 2


# ----------------------------
# ❌ Failure Cases
# ----------------------------


async def test_similarity_search_empty_question(monkeypatch, test_user):
    """Test: raises ValueError if question is an empty string."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    with pytest.raises(ValueError):
        await vector_svc.search(
            question="",
            user=test_user,
            top_k=3,
            document_library_tags_ids=None,
            policy_name=SearchPolicyName.semantic,
        )


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


async def test_similarity_search_zero_k(monkeypatch, test_user):
    """Test: returns empty list when k=0, a valid edge case."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    results = await vector_svc.search(
        question="Explain edge case.",
        user=test_user,
        top_k=0,
        document_library_tags_ids=None,
        policy_name=SearchPolicyName.semantic,
    )
    assert isinstance(results, list)
    assert results == []


async def test_hybrid_policy_falls_back_to_semantic_when_backend_unsupported(monkeypatch, test_user):
    """Test: hybrid policy should not crash when backend lacks hybrid_search; falls back to semantic."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    results = await vector_svc.search(
        question="What is AI?",
        user=test_user,
        top_k=2,
        document_library_tags_ids=None,
        policy_name=SearchPolicyName.hybrid,
    )
    assert isinstance(results, list)
    assert len(results) == 2


async def test_strict_policy_falls_back_to_semantic_when_backend_unsupported(monkeypatch, test_user):
    """Test: strict policy should not crash when backend lacks full_text_search; falls back to semantic."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    results = await vector_svc.search(
        question="What is AI?",
        user=test_user,
        top_k=2,
        document_library_tags_ids=None,
        policy_name=SearchPolicyName.strict,
    )
    assert isinstance(results, list)
    assert len(results) == 2


async def test_search_mixes_library_scope_and_document_scope_as_union(monkeypatch, test_user):
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()

    async def _fake_search_fn(*, question, user, k, library_tags_ids=None, metadata_terms_extra=None):
        assert question == "What changed?"
        assert k == 5
        if library_tags_ids is not None:
            return [
                vector_search_service.VectorSearchHit(
                    uid="doc-lib",
                    title="Library doc",
                    file_name="library.md",
                    content="library hit",
                    score=0.91,
                    tag_ids=["tag-1"],
                    tag_names=[],
                    tag_full_paths=[],
                )
            ]
        if metadata_terms_extra and metadata_terms_extra.get("document_uid") == ["doc-picked"]:
            return [
                vector_search_service.VectorSearchHit(
                    uid="doc-picked",
                    title="Picked doc",
                    file_name="picked.md",
                    content="picked hit",
                    score=0.87,
                    tag_ids=[],
                    tag_names=[],
                    tag_full_paths=[],
                )
            ]
        return []

    vector_svc._hybrid = _fake_search_fn  # type: ignore[method-assign]

    results = await vector_svc.search(
        question="What changed?",
        user=test_user,
        top_k=5,
        document_library_tags_ids=["tag-1"],
        document_uids=["doc-picked"],
        policy_name=SearchPolicyName.hybrid,
        include_session_scope=False,
        include_corpus_scope=True,
    )

    assert [hit.uid for hit in results] == ["doc-lib", "doc-picked"]


async def test_search_document_scope_only_does_not_widen_to_libraries(monkeypatch, test_user):
    """document_uids WITHOUT library tags must search ONLY the named documents.

    Regression: previously the library branch still ran over ALL authorized tags
    and was unioned in, leaking the whole tagged corpus into a document-scoped
    search (which broke the comparison agent). The library branch must not run.
    """
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()

    library_branch_calls: list[object] = []

    async def _fake_search_fn(*, question, user, k, library_tags_ids=None, metadata_terms_extra=None):
        if library_tags_ids is not None:
            library_branch_calls.append(library_tags_ids)
            return [
                vector_search_service.VectorSearchHit(
                    uid="doc-lib",
                    title="Library doc",
                    file_name="library.md",
                    content="library hit",
                    score=0.91,
                    tag_ids=["tag-1"],
                    tag_names=[],
                    tag_full_paths=[],
                )
            ]
        if metadata_terms_extra and metadata_terms_extra.get("document_uid") == ["doc-picked"]:
            return [
                vector_search_service.VectorSearchHit(
                    uid="doc-picked",
                    title="Picked doc",
                    file_name="picked.md",
                    content="picked hit",
                    score=0.87,
                    tag_ids=[],
                    tag_names=[],
                    tag_full_paths=[],
                )
            ]
        return []

    vector_svc._hybrid = _fake_search_fn  # type: ignore[method-assign]

    results = await vector_svc.search(
        question="What changed?",
        user=test_user,
        top_k=5,
        document_library_tags_ids=None,  # no library scope — documents only
        document_uids=["doc-picked"],
        policy_name=SearchPolicyName.hybrid,
        include_session_scope=False,
        include_corpus_scope=True,
    )

    # ONLY the named document is returned; the library branch never ran.
    assert [hit.uid for hit in results] == ["doc-picked"]
    assert library_branch_calls == []


async def test_selected_document_cannot_escape_team_and_does_not_filter_attachments(monkeypatch, test_user):
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    service = VectorSearchService()
    calls = []

    async def search(**kwargs):
        calls.append(kwargs)
        return []

    service._hybrid = search
    await service.search(question="test", user=test_user, document_library_tags_ids=None, document_uids=["doc-picked", "foreign"], team_id="team-a", session_id="session-a")
    assert len(calls) == 2
    assert calls[0]["metadata_terms_extra"] == {"user_id": [test_user.uid], "session_id": ["session-a"], "scope": ["session"]}
    assert calls[1]["metadata_terms_extra"]["document_uid"] == ["doc-picked"]
    calls.clear()

    async def forbidden_corpus_call(*args, **kwargs):
        raise AssertionError("Attachment-only search must not enumerate corpus rights")

    service.tag_service.list_authorized_tags_ids = forbidden_corpus_call
    await service.search(question="test", user=test_user, document_library_tags_ids=None, session_id="session-a", include_corpus_scope=False)
    assert len(calls) == 1
