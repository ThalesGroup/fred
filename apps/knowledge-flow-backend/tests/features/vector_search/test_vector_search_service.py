# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Similarity uses the published search boundary before the existing cross-encoder."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid5

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.documents.access import SearchScope
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.security.delegation import AssertedUser
from fred_core.store.vector_search import VectorSearchHit
from fred_knowledge.vector.base_vector_store import BaseVectorHit
from langchain_core.documents import Document

from knowledge_flow_backend.features.vector_search import vector_search_service as module

SPACE, DOC, OUTSIDE, HIDDEN, ATTACHMENT, GENERATION = [UUID(int=i) for i in range(1, 7)]


@pytest.fixture
def search(monkeypatch):
    service = module.VectorSearchService.__new__(module.VectorSearchService)
    service._corpus = AsyncMock(return_value=SimpleNamespace())
    service.kpi = MagicMock()
    # Exercise rerank_documents itself: reverse relevance, without changing retrieval scores.
    service._crossencoder_model = SimpleNamespace(predict=MagicMock(side_effect=lambda pairs: list(range(len(pairs)))))
    service._to_hit = AsyncMock(side_effect=lambda doc, score, rank, user: VectorSearchHit(uid=doc.metadata["document_uid"], title="Doc", content=doc.page_content, score=score, rank=rank))
    scope = SearchScope(SPACE, (SPACE,), DocumentScope.from_ids(document_ids=[str(DOC), str(HIDDEN), str(ATTACHMENT)]))
    engine = MagicMock()
    conn = engine.connect.return_value.__aenter__.return_value
    result = MagicMock()
    facts = dict(space_id=SPACE, visible=True, rejection_reasons=[], generation_id=GENERATION, vector_ordinals=list(range(110)), folder_id=None, session_id=None)
    result.mappings.return_value.all.return_value = [
        dict(facts, id=DOC),
        dict(facts, id=OUTSIDE),
        dict(facts, id=HIDDEN, visible=False),
        dict(facts, id=ATTACHMENT, session_id=UUID(int=99), session_user_id="alice"),
    ]
    conn.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(module.ApplicationContext, "get_instance", lambda: SimpleNamespace(get_pg_async_engine=lambda: engine))
    monkeypatch.setattr(module, "organization_model", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "resolve_scope", AsyncMock(return_value=scope))

    def hit(ordinal, score=0.9, uid=DOC):
        return BaseVectorHit(document=Document(page_content=f"{uid}:{ordinal}", metadata={"document_uid": str(uid), "chunk_uid": str(uuid5(GENERATION, str(ordinal)))}), score=score)

    candidates = [hit(i, score) for i, score in enumerate([0.9, 0.8, 0.7, 0.6, 0.4, 0.1])]
    strategy = AsyncMock(side_effect=lambda store, **kwargs: candidates[: kwargs["k"]])
    service._hybrid = strategy
    args = dict(
        question="anchor",
        user=AssertedUser(uid="alice", client_id="pod", run_id="turn", agent_id="agent"),
        top_k=2,
        policy_name=None,
        context=DocumentAccessContext(space_id=SPACE, document_scope=scope.document_scope),
        authorized_space_ids=(SPACE,),
    )
    return SimpleNamespace(service=service, args=args, candidates=candidates, hit=hit, strategy=strategy, conn=conn, scope=scope)


@pytest.mark.asyncio
async def test_default_and_explicit_defaults_preserve_exact_hits_and_order(search):
    implicit = await search.service.search(**search.args)
    explicit = await search.service.search(**search.args, rerank=False, min_score=None)
    expected = [VectorSearchHit(uid=str(DOC), title="Doc", content=f"{DOC}:{i}", score=score, rank=i + 1) for i, score in enumerate([0.9, 0.8])]
    assert [hit.model_dump_json() for hit in implicit] == [hit.model_dump_json() for hit in explicit] == [hit.model_dump_json() for hit in expected]
    assert all(call.kwargs["k"] == 2 for call in search.strategy.call_args_list)
    search.service.crossencoder_model.predict.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("min_score,expected", [(None, [(5, 0.1), (4, 0.4)]), (0.3, [(4, 0.4)])])
async def test_rerank_sees_only_visible_selected_published_corpus_then_filters_scores(search, min_score, expected):
    # Simulate a stale/misbehaving index: none of these candidates may reach the model.
    search.candidates[:0] = [search.hit(0, uid=OUTSIDE), search.hit(0, uid=HIDDEN), search.hit(0, uid=ATTACHMENT), search.hit(999)]
    hits = await search.service.search(**search.args, rerank=True, min_score=min_score)
    call = search.strategy.call_args.kwargs
    assert call["k"] == 10
    assert call["question"] == "anchor"
    assert call["metadata_terms_extra"] == {"space_id": [str(SPACE)], "session_id": [""]}
    assert call["metadata_any"] == search.scope.selection_terms
    search.conn.execute.assert_awaited_once()
    assert "cp_read.document_visibility" in str(search.conn.execute.call_args.args[0])
    search.service.crossencoder_model.predict.assert_called_once_with([("anchor", f"{DOC}:{i}") for i in range(6)])
    assert [(hit.content, hit.score) for hit in hits] == [(f"{DOC}:{i}", score) for i, score in expected]
    # Filtering follows top_r: the higher-score third result does not backfill a dropped hit.
    assert [hit.rank for hit in hits] == ([6, 5] if min_score is None else [5])


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k,pool", [(1, 5), (20, 100), (21, 100), (100, 100)])
async def test_rerank_pool_and_return_limit(search, top_k, pool):
    search.candidates[:] = [search.hit(i) for i in range(110)]
    hits = await search.service.search(**{**search.args, "top_k": top_k}, rerank=True)
    assert search.strategy.call_args.kwargs["k"] == pool
    pairs = search.service.crossencoder_model.predict.call_args.args[0]
    assert len(pairs) == pool
    assert [hit.content for hit in hits] == [f"{DOC}:{i}" for i in range(pool - 1, pool - top_k - 1, -1)]


@pytest.mark.asyncio
async def test_min_score_without_rerank_keeps_retrieval_order_and_inclusive_threshold(search):
    search.candidates[:] = [search.hit(0, 0.0), search.hit(1, -0.1), search.hit(2, 0.5)]
    hits = await search.service.search(**{**search.args, "top_k": 3}, min_score=0.0)
    assert [(hit.content, hit.score) for hit in hits] == [(f"{DOC}:0", 0.0), (f"{DOC}:2", 0.5)]
    assert search.strategy.call_args.kwargs["k"] == 3
    search.service.crossencoder_model.predict.assert_not_called()


@pytest.mark.asyncio
async def test_no_visible_hits_never_loads_or_calls_the_reranker(search):
    search.candidates[:] = [search.hit(0, uid=HIDDEN)]
    assert await search.service.search(**search.args, rerank=True) == []
    search.service.crossencoder_model.predict.assert_not_called()


@pytest.mark.parametrize(
    "options,expected",
    [
        ({}, [(0, 0.9), (1, 0.8)]),
        ({"rerank": False, "min_score": None}, [(0, 0.9), (1, 0.8)]),
        ({"rerank": True, "min_score": 0.3}, [(4, 0.4)]),
        ({"min_score": 0.85}, [(0, 0.9)]),
    ],
)
def test_documents_search_transports_options_and_serializes_original_scores(monkeypatch, search, options, expected):
    from knowledge_flow_backend.features.vector_search import vector_search_controller as controller

    monkeypatch.setattr(controller, "VectorSearchService", lambda: search.service)
    monkeypatch.setattr(controller, "get_kpi_writer", MagicMock)
    monkeypatch.setattr(controller, "phase_timer", lambda *_args: nullcontext())
    admission = AsyncMock(return_value=(SPACE,))
    monkeypatch.setattr(controller, "require_space_read", admission)
    app, router = FastAPI(), APIRouter()
    controller.VectorSearchController(router)
    app.include_router(router)
    app.dependency_overrides[controller.delegated_person] = lambda: search.args["user"]
    with TestClient(app) as client:
        response = client.post("/documents/search", json={"question": "anchor", "top_k": 2, **options}, headers={DOCUMENT_CONTEXT_HEADER: search.args["context"].model_dump_json()})
    assert response.status_code == 200
    admission.assert_awaited_once_with(search.args["user"], SPACE)
    assert [(hit["content"], hit["score"]) for hit in response.json()] == [(f"{DOC}:{i}", score) for i, score in expected]


def test_simultaneous_first_reranks_load_crossencoder_once(monkeypatch):
    loading, contended = Event(), Event()
    model = SimpleNamespace(predict=MagicMock(return_value=[0.1, 0.9]))

    def load():
        loading.set()
        # Keep initialization in flight until the second rerank tries the lock.
        assert contended.wait(timeout=5)
        return model

    context = MagicMock()
    context.get_crossencoder_model.side_effect = load
    monkeypatch.setattr(module.ApplicationContext, "get_instance", lambda: context)
    service = module.VectorSearchService()
    context.get_crossencoder_model.assert_not_called()
    context.get_corpus_store.assert_not_called()
    lock = service._crossencoder_lock

    def enter():
        if loading.is_set():
            contended.set()
        return lock.__enter__()

    observed_lock = MagicMock()
    observed_lock.__enter__.side_effect = enter
    observed_lock.__exit__.side_effect = lock.__exit__
    monkeypatch.setattr(service, "_crossencoder_lock", observed_lock)
    hits = [VectorSearchHit(uid=str(DOC), title="Doc", content=str(i), score=score) for i, score in enumerate([0.8, 0.2])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.rerank_documents, "anchor", hits, 2)
        assert loading.wait(timeout=5)
        second = pool.submit(service.rerank_documents, "anchor", hits, 2)
        results = [first.result(timeout=5), second.result(timeout=5)]

    context.get_crossencoder_model.assert_called_once_with()
    assert service.crossencoder_model is model
    assert observed_lock.__enter__.call_count == 2
    assert model.predict.call_count == 2
    for result in results:
        assert result == [hits[1], hits[0]]
        assert [hit.score for hit in result] == [0.2, 0.8]


@pytest.mark.asyncio
async def test_unreachable_vector_store_is_reported_as_not_ready(monkeypatch):
    context = MagicMock()
    context.get_corpus_store.side_effect = OSError("unreachable")
    monkeypatch.setattr(module.ApplicationContext, "get_instance", lambda: context)
    monkeypatch.setattr(module, "organization_model", AsyncMock(return_value=SimpleNamespace(organization_id=UUID(int=7), admission=object())))
    with pytest.raises(HTTPException) as failure:
        await module.VectorSearchService()._corpus(DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope()))
    assert failure.value.detail == "corpus_not_ready"


@pytest.mark.asyncio
async def test_the_question_is_embedded_only_with_the_locked_corpus_model(monkeypatch):
    """No locked model or no index yet: an empty result, never another model or index."""
    context = MagicMock()
    monkeypatch.setattr(module.ApplicationContext, "get_instance", lambda: context)
    scope = DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope())
    service = module.VectorSearchService()
    monkeypatch.setattr(module, "organization_model", AsyncMock(return_value=None))
    assert await service._corpus(scope) is None
    context.get_corpus_store.assert_not_called()
    model = SimpleNamespace(organization_id=UUID(int=7), admission=object())
    monkeypatch.setattr(module, "organization_model", AsyncMock(return_value=model))
    context.get_corpus_store.return_value = SimpleNamespace(index_exists=lambda: False)
    assert await service._corpus(scope) is None
    context.get_corpus_store.assert_called_once_with(model.organization_id, model.admission)
    monkeypatch.setattr(module, "organization_model", AsyncMock(side_effect=module.OrganizationModelUnavailable("withdrawn")))
    with pytest.raises(HTTPException) as failure:
        await service._corpus(scope)
    assert failure.value.detail == "corpus_model_unavailable"
