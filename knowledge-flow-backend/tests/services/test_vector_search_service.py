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
    Records every search_filter it receives so tests can assert on scoping.
    """

    def __init__(self):
        self.calls: list = []

    def ann_search(self, query, *, k=10, search_filter=None):
        self.calls.append(search_filter)
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
    async def list_authorized_tags_ids(self, _user, _owner_filter=None, _team_id=None):
        # Non-empty authorized scope so corpus search path is exercised in unit tests.
        return {"tag-1"}

    async def get_tag_for_user(self, _tag_id, _user):
        return DummyTag()


class DummyMetadataService:
    async def filter_readable_document_uids(self, _user, document_uids):
        return set(document_uids or [])


class DummyMetadataServiceNoCorpusDocs:
    """Simulates document_uids that are NOT readable corpus documents (e.g. session
    attachments): the corpus ReBAC filter drops them all."""

    async def filter_readable_document_uids(self, _user, _document_uids):
        return set()


def _document_uid_terms(search_filter):
    """Extract the document_uid term filter a search_filter carries, if any."""
    if search_filter is None or not search_filter.metadata_terms:
        return None
    return search_filter.metadata_terms.get("document_uid")


def _is_corpus_filter(search_filter):
    """A corpus-scope query is the one excluding session vectors (scope=!session)."""
    if search_filter is None or not search_filter.metadata_terms:
        return False
    return list(search_filter.metadata_terms.get("scope") or []) == ["!session"]


class DummyContext:
    """
    Mock application context that returns dummy embedder and vector store.

    Reuses a single vector store instance per context so tests can inspect the
    search filters it recorded.
    """

    def __init__(self):
        self.vector_store = DummyVectorStore()

    def get_embedder(self):
        return "dummy_embedder"

    def get_create_vector_store(self, embedder):
        return self.vector_store

    def get_crossencoder_model(self):
        return None

    def get_kpi_writer(self):
        return DummyKPI()


@pytest.fixture
def test_user():
    return KeycloakUser(uid="test-user", username="testuser", email="testuser@localhost", roles=["admin"], groups=["admins"])


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


# ----------------------------
# 🔒 document_uids scoping
# ----------------------------


async def test_document_uids_skip_corpus_when_not_readable_corpus_docs(monkeypatch, test_user):
    """Requested uids that are not readable corpus documents (e.g. session attachments)
    must NOT cause an unfiltered corpus search — the corpus scope is skipped entirely.

    This is the regression guard for the leak where a session-attachment uid filter,
    dropped by corpus ReBAC, degraded the corpus query to "return the whole library".
    """
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataServiceNoCorpusDocs)
    vector_svc = VectorSearchService()
    await vector_svc.search(
        question="What is in the attachment?",
        user=test_user,
        top_k=5,
        document_library_tags_ids=None,
        document_uids=["attachment-uid"],
        policy_name=SearchPolicyName.semantic,
        session_id="session-1",
    )

    # No corpus query should have run at all — the requested uid was not a readable
    # corpus document, so the corpus scope is skipped rather than searched unfiltered.
    # (Asserting on the recorded filters, not returned hits: the dummy store does not
    # itself apply metadata filters.)
    calls = vector_svc.vector_store.calls
    assert not any(_is_corpus_filter(sf) for sf in calls)


async def test_document_uids_filter_attachment_scope_by_requested_uids(monkeypatch, test_user):
    """The session/attachment query must be filtered by the caller's requested uids
    verbatim — not by the corpus-ReBAC-filtered set (which never contains attachment
    uids)."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataServiceNoCorpusDocs)
    vector_svc = VectorSearchService()
    await vector_svc.search(
        question="What is in the attachment?",
        user=test_user,
        top_k=5,
        document_library_tags_ids=None,
        document_uids=["attachment-uid"],
        policy_name=SearchPolicyName.semantic,
        session_id="session-1",
    )

    attachment_calls = [sf for sf in vector_svc.vector_store.calls if sf is not None and sf.metadata_terms and list(sf.metadata_terms.get("scope") or []) == ["session"]]
    assert attachment_calls, "expected a session-scope attachment query"
    assert list(_document_uid_terms(attachment_calls[0]) or []) == ["attachment-uid"]


async def test_document_uids_filter_corpus_scope_by_readable_uids(monkeypatch, test_user):
    """When requested uids ARE readable corpus documents, the corpus query is filtered
    by them (the normal corpus case is preserved)."""
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    vector_svc = VectorSearchService()
    await vector_svc.search(
        question="What is AI?",
        user=test_user,
        top_k=5,
        document_library_tags_ids=None,
        document_uids=["doc-1"],
        policy_name=SearchPolicyName.semantic,
    )

    corpus_calls = [sf for sf in vector_svc.vector_store.calls if _is_corpus_filter(sf)]
    assert corpus_calls, "expected a corpus-scope query"
    assert list(_document_uid_terms(corpus_calls[0]) or []) == ["doc-1"]
