# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Corpus access uses canonical turn authority and refuses unsupported sources."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_capability_document_access.search import CorpusSearch
from fred_runtime.integrations.v2_runtime.adapters import DocumentSearchAdapter
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    DocumentPortCallError,
    DocumentScopeRefusedError,
    DocumentSearchResult,
)
from weaver_fixtures import resolved_binding


class _Corpus:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    async def search(self, query: str, **kwargs: Any) -> DocumentSearchResult:
        self.calls.append(kwargs)
        kwargs["check_active"]()
        if self.error:
            raise self.error
        return DocumentSearchResult()


def _adapter(
    corpus: _Corpus | None, **fields: Any
) -> tuple[DocumentSearchAdapter, TurnAuthority]:
    binding = resolved_binding()
    authority = TurnAuthority(binding, None)
    context = RuntimeContext(
        user_id=binding.subject_id,
        session_id=binding.conversation_id,
        space_id=str(binding.space.id),
        agent_instance_id=str(binding.agent.instance_id),
        **fields,
    )
    bound = BoundRuntimeContext(
        runtime_context=context,
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor=binding.subject_id,
            tenant=str(binding.space.id),
            environment=PortableEnvironment.DEV,
        ),
    )
    return DocumentSearchAdapter(
        binding=bound, corpus=cast(CorpusSearch | None, corpus)
    ), authority


@pytest.mark.asyncio
@pytest.mark.parametrize("rag_scope", ["hybrid", "corpus_only", "general_only"])
@pytest.mark.parametrize("corpus_enabled", [True, False])
async def test_sources_bound_the_turn_scope(
    rag_scope: str, corpus_enabled: bool
) -> None:
    corpus = _Corpus()
    adapter, authority = _adapter(corpus, search_rag_scope=rag_scope)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        result = await adapter.search(
            "q", include_attachments=False, include_team_documents=corpus_enabled
        )
    assert result.hits == ()
    if rag_scope == "general_only" or not corpus_enabled:
        assert corpus.calls == []
    else:
        assert corpus.calls[0]["space_id"] == authority.binding.space.id


@pytest.mark.asyncio
async def test_general_only_overrides_explicit_corpus_scope() -> None:
    corpus = _Corpus()
    adapter, authority = _adapter(
        corpus, search_rag_scope="general_only", include_corpus_scope=True
    )
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        result = await adapter.search(
            "q", include_team_documents=True, include_attachments=False
        )
    assert result.hits == ()
    assert corpus.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "restriction",
    [
        {"include_attachments": True},
        {"library_tag_ids": ["library"]},
        {"document_uids": ["document"]},
    ],
)
async def test_unsupported_scope_is_refused(restriction: dict[str, Any]) -> None:
    corpus = _Corpus()
    adapter, authority = _adapter(corpus)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        with pytest.raises(DocumentScopeRefusedError):
            await adapter.search("q", **{"include_attachments": False, **restriction})
    assert corpus.calls == []


@pytest.mark.asyncio
async def test_empty_scope_does_not_read_corpus() -> None:
    corpus = _Corpus()
    adapter, authority = _adapter(corpus)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        assert (
            await adapter.search("q", include_attachments=False, document_uids=[])
        ).hits == ()
    assert corpus.calls == []


@pytest.mark.asyncio
async def test_closed_or_missing_turn_cannot_read_corpus() -> None:
    corpus = _Corpus()
    adapter, authority = _adapter(corpus)
    with pytest.raises(AuthorityLostError):
        await adapter.search("q", include_attachments=False)
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        authority.close()
        with pytest.raises(AuthorityLostError):
            await adapter.search("q", include_attachments=False)
    assert corpus.calls == []


@pytest.mark.asyncio
async def test_failure_is_not_an_empty_result() -> None:
    adapter, authority = _adapter(_Corpus(TimeoutError("private transport details")))
    with RunScope.open() as scope:
        scope.turn_authority = authority
        authority.start(scope)
        with pytest.raises(DocumentPortCallError) as exc:
            await adapter.search("q", include_attachments=False)
    assert exc.value.timed_out
    assert "private transport" not in str(exc.value)
