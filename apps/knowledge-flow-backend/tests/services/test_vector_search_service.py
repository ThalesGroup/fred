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

import asyncio
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fred_core import DocumentPermission, KeycloakUser
from fred_core.common import OwnerFilter
from fred_core.security.delegation import DelegationConfig, initialize_delegation, preserved_delegation
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import AnnHit
from knowledge_flow_backend.features.metadata.service import MetadataService
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
    async def list_authorized_tags_ids(self, _user, _owner_filter=None, _team_id=None):
        # Non-empty authorized scope so corpus search path is exercised in unit tests.
        return {"tag-1"}

    async def get_tag_for_user(self, _tag_id, _user):
        return DummyTag()


class DummyMetadataService:
    @property
    def metadata_store(self):
        return self

    async def get_metadata_by_uids(self, uids):
        return [SimpleNamespace(identity=SimpleNamespace(document_uid=uid), tags=SimpleNamespace(tag_ids=["tag-1"])) for uid in uids]

    async def filter_readable_document_uids(self, _user, document_uids):
        return set(document_uids or [])


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
            return [AnnHit(document=Document(page_content="library hit", metadata={"document_uid": "doc-lib", "scope": "corpus"}), score=0.91)]
        if metadata_terms_extra and metadata_terms_extra.get("document_uid") == ["doc-picked"]:
            return [AnnHit(document=Document(page_content="picked hit", metadata={"document_uid": "doc-picked", "scope": "corpus"}), score=0.87)]
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
            return [AnnHit(document=Document(page_content="library hit", metadata={"document_uid": "doc-lib", "scope": "corpus"}), score=0.91)]
        if metadata_terms_extra and metadata_terms_extra.get("document_uid") == ["doc-picked"]:
            return [AnnHit(document=Document(page_content="picked hit", metadata={"document_uid": "doc-picked", "scope": "corpus"}), score=0.87)]
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


class SnapshotStore:
    """Apply index predicates to a snapshot that can differ from canonical metadata."""

    def __init__(self):
        self.hits = []
        self.calls = []

    def ann_search(self, query, *, k, search_filter):
        self.calls.append(search_filter)
        result = []
        for hit in self.hits:
            md = hit.document.metadata
            if search_filter.tag_ids and not set(search_filter.tag_ids).intersection(md.get("tag_ids", [])):
                continue
            if any((md.get(key) == "session" if values == ["!session"] else md.get(key) not in values) for key, values in (search_filter.metadata_terms or {}).items()):
                continue
            result.append(hit)
        return result[:k]

    def full_text_search(self, query, top_k, search_filter):
        return self.ann_search(query, k=top_k, search_filter=search_filter)

    def hybrid_search(self, query, top_k, search_filter):
        return self.ann_search(query, k=top_k, search_filter=search_filter)


class CurrentMetadata:
    def __init__(self):
        self.tags = {}
        self.batches = []
        self.checks = Counter()
        self.denied = set()
        self.error = None
        self.active = 0
        self.peak = 0

    async def get_metadata_by_uids(self, uids):
        self.batches.append(list(uids))
        return [SimpleNamespace(identity=SimpleNamespace(document_uid=uid), tags=SimpleNamespace(tag_ids=self.tags[uid])) for uid in uids if uid in self.tags]

    async def has_user_permission(self, user, permission, uid):
        assert permission == DocumentPermission.READ
        self.checks[uid] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0)
            if self.error:
                raise self.error
            return uid not in self.denied
        finally:
            self.active -= 1


def candidate(uid, *tags, **metadata):
    return AnnHit(document=Document(page_content=f"content-{uid}", metadata={"document_uid": uid, "tag_ids": list(tags), "scope": "corpus", "retrievable": True, **metadata}), score=0.9)


@pytest.fixture
def guarded_search(monkeypatch, test_user):
    monkeypatch.setattr(vector_search_service.ApplicationContext, "get_instance", DummyContext)
    monkeypatch.setattr(vector_search_service, "TagService", DummyTagService)
    monkeypatch.setattr(vector_search_service, "MetadataService", DummyMetadataService)
    svc = VectorSearchService()
    store, current = SnapshotStore(), CurrentMetadata()
    metadata = MetadataService.__new__(MetadataService)
    metadata.metadata_store = current
    metadata.rebac = current
    svc.vector_store, svc.metadata_service = store, metadata
    calls = []

    async def authorized_tags(user, owner_filter, team_id):
        calls.append((owner_filter, team_id))
        return {"a", "a2"} if owner_filter == OwnerFilter.TEAM else {"a", "a2", "b"}

    svc.tag_service.list_authorized_tags_ids = authorized_tags

    async def run(**kwargs):
        return await svc.search(
            question="needle",
            user=test_user,
            top_k=100,
            document_library_tags_ids=kwargs.pop("libraries", None),
            owner_filter=kwargs.pop("owner_filter", OwnerFilter.TEAM),
            team_id=kwargs.pop("team_id", "team-a"),
            **kwargs,
        )

    return svc, store, current, calls, run


@pytest.mark.parametrize("policy", list(SearchPolicyName))
@pytest.mark.parametrize("libraries", [None, ["a"]])
async def test_explicit_document_ids_cannot_escape_team(guarded_search, policy, libraries):
    svc, store, current, calls, run = guarded_search
    current.tags = {"outside": ["b"], "inside": ["a"], "extra": ["a"]}
    store.hits = [candidate(uid, *tags) for uid, tags in current.tags.items()]
    hits = await run(libraries=libraries, document_uids=["outside", "inside"], policy_name=policy)
    assert {h.uid for h in hits} == ({"inside", "extra"} if libraries else {"inside"})
    assert "outside" not in current.checks
    assert len(calls) == 1


@pytest.mark.parametrize("policy", list(SearchPolicyName))
@pytest.mark.parametrize("read_denied", [False, True])
async def test_stale_library_membership_is_rejected_before_enrichment(guarded_search, policy, read_denied):
    svc, store, current, calls, run = guarded_search
    current.tags = {"moved": ["b"], "valid": ["a", "b"]}
    store.hits = [candidate("moved", "a", "b"), candidate("valid", "a", "b"), candidate("deleted", "a")]
    current.denied = {"moved"} if read_denied else set()
    enriched = []
    original = svc._to_hit

    async def enrich(doc, *args):
        enriched.append(doc.metadata["document_uid"])
        return await original(doc, *args)

    svc._to_hit = enrich
    hits = await run(libraries=["a"], policy_name=policy)
    assert [h.uid for h in hits] == enriched == ["valid"]
    assert hits[0].tag_ids == ["a"]
    assert current.checks == {"valid": 1}
    # A caller with access to B still cannot retrieve the moved document via A.
    assert [h.uid for h in await run(libraries=["a"], owner_filter=None)] == ["valid"]
    if not read_denied:
        assert "moved" in {h.uid for h in await run(libraries=["b"], owner_filter=None)}


async def test_denied_and_missing_documents_do_not_widen_search(guarded_search):
    svc, store, current, calls, run = guarded_search
    current.tags = {"denied": ["a"], "valid": ["a"]}
    current.denied = {"denied"}
    store.hits = [candidate("denied", "a"), candidate("valid", "a")]
    assert await run(document_uids=["missing", "denied"]) == []
    assert store.calls == []
    assert [h.uid for h in await run(libraries=["a"])] == ["valid"]
    assert await run(libraries=["unknown"]) == []


async def test_authority_failure_never_enriches_candidates(guarded_search):
    svc, store, current, calls, run = guarded_search
    current.tags = {"valid": ["a"]}
    store.hits = [candidate("valid", "a")]
    current.error = TimeoutError("authority unavailable")

    async def unexpected(*args, **kwargs):
        pytest.fail("unchecked candidate reached enrichment")

    svc._to_hit = unexpected
    with pytest.raises(TimeoutError, match="authority unavailable"):
        await run(libraries=["a"])


@pytest.mark.parametrize("irrelevant", [0, 1000])
async def test_checks_are_bounded_and_deduplicated_across_chunks_and_branches(guarded_search, irrelevant):
    svc, store, current, calls, run = guarded_search
    uids = [f"doc-{n}" for n in range(37)]
    current.tags = {uid: ["a"] for uid in uids} | {f"other-{n}": ["b"] for n in range(irrelevant)}
    store.hits = [candidate(uid, "a", chunk_index=n) for uid in uids for n in range(2)]
    hits = await run(libraries=["a"], document_uids=[uids[0]])
    assert {h.uid for h in hits} == set(uids)
    assert current.checks == {uid: 1 for uid in uids}
    assert current.peak <= 10
    assert sum(map(len, current.batches)) == len(uids)
    assert len(calls) == 1


async def test_request_cache_does_not_survive_membership_change(guarded_search):
    svc, store, current, calls, run = guarded_search
    current.tags = {"moved": ["a"]}
    store.hits = [candidate("moved", "a")]
    assert len(await run()) == 1
    current.tags["moved"] = ["b"]
    assert await run() == []


@pytest.mark.parametrize("policy", list(SearchPolicyName))
async def test_corpus_selection_keeps_only_current_users_session_attachments(guarded_search, policy, test_user):
    svc, store, current, calls, run = guarded_search
    current.tags = {"corpus": ["a"]}
    store.hits = [
        candidate("corpus", "a"),
        candidate("attachment", scope="session", user_id=test_user.uid, session_id="session"),
        candidate("foreign", scope="session", user_id="other", session_id="session"),
        candidate("other-session", scope="session", user_id=test_user.uid, session_id="elsewhere"),
    ]
    hits = await run(document_uids=["corpus"], session_id="session", policy_name=policy)
    assert {h.uid for h in hits} == {"attachment", "corpus"}
    assert current.checks == {"corpus": 1}
    assert {h.uid for h in await run(document_uids=["corpus"], session_id="session", include_session_scope=False)} == {"corpus"}
    assert {h.uid for h in await run(document_uids=["corpus"], session_id="session", include_corpus_scope=False)} == {"attachment"}


@pytest.mark.parametrize("owner_filter", [None, OwnerFilter.PERSONAL])
async def test_unscoped_and_personal_ownership_resolution_is_preserved(guarded_search, owner_filter):
    svc, store, current, calls, run = guarded_search
    current.tags = {"picked": ["b"]}
    store.hits = [candidate("picked", "b")]
    assert [h.uid for h in await run(document_uids=["picked"], owner_filter=owner_filter, team_id=None)] == ["picked"]
    assert calls == [(owner_filter, None)]


@pytest.mark.parametrize("delegated", [False, True])
async def test_service_agent_uses_team_policy_but_delegated_user_still_needs_read(guarded_search, test_user, delegated):
    svc, store, current, calls, run = guarded_search
    current.tags = {"team": ["a"], "outside": ["b"]}
    store.hits = [candidate("team", "a"), candidate("outside", "a")]
    current.denied = {"team"}
    test_user.roles = ["service_agent"]
    if delegated:
        test_user.client_id = "agents"
        test_user.caller_roles = frozenset({"delegation_caller"})
    with preserved_delegation():
        initialize_delegation(DelegationConfig(accept_delegated_calls=True))
        hits = await run(libraries=["a"])
    assert [h.uid for h in hits] == ([] if delegated else ["team"])
    assert current.checks == ({"team": 1} if delegated else {})
