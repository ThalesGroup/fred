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
"""Table-aware post-processing of `knowledge.search` hits.

Similarity ranking returns a large table's chunks shuffled and truncated, and the
splitter repeats the header on each one. Left alone the model reads that as several
small unrelated tables and answers row questions wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolInvocationRequest,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.support.builtins.catalog import TOOL_REF_KNOWLEDGE_SEARCH

HEADER = "| name | default |\n| --- | --- |"
NO_LEADING_PIPE = "name | default\n--- | ---"


def _hit(
    uid: str, content: str, *, chunk_index: int | None = None, score: float = 0.9
) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid,
        title=uid,
        content=content,
        score=score,
        type="document",
        chunk_index=chunk_index,
    )


# --------------------------------------------------------------------------- #
# _table_header_span
# --------------------------------------------------------------------------- #


def test_header_span_detects_table_with_leading_pipe():
    assert adapters_module._table_header_span(f"{HEADER}\n| a | 1 |") == 2


def test_header_span_detects_table_without_leading_pipe():
    """The splitter accepts these, so the dedup must recognise them too."""
    assert adapters_module._table_header_span(f"{NO_LEADING_PIPE}\na | 1") == 2


def test_header_span_rejects_prose_containing_pipes():
    assert (
        adapters_module._table_header_span("use a | b to pipe\nthen read the result")
        == 0
    )


def test_header_span_rejects_single_line():
    assert adapters_module._table_header_span("| name | default |") == 0


# --------------------------------------------------------------------------- #
# _restore_document_order
# --------------------------------------------------------------------------- #


def test_chunks_of_one_document_are_reordered_by_index():
    hits = [
        _hit("d1", "third", chunk_index=3),
        _hit("d1", "first", chunk_index=1),
        _hit("d1", "second", chunk_index=2),
    ]

    ordered = adapters_module._restore_document_order(hits)

    assert [h.content for h in ordered] == ["first", "second", "third"]


def test_documents_keep_their_relative_ranking():
    hits = [
        _hit("d2", "b", chunk_index=5),
        _hit("d1", "a", chunk_index=1),
        _hit("d2", "a", chunk_index=1),
    ]

    ordered = adapters_module._restore_document_order(hits)

    assert [h.uid for h in ordered] == ["d2", "d2", "d1"]


def test_chunks_without_index_sort_last():
    """Documents indexed before chunk_index existed degrade, they do not jump the queue."""
    hits = [_hit("d1", "legacy"), _hit("d1", "indexed", chunk_index=2)]

    ordered = adapters_module._restore_document_order(hits)

    assert [h.content for h in ordered] == ["indexed", "legacy"]


# --------------------------------------------------------------------------- #
# _strip_repeated_table_headers
# --------------------------------------------------------------------------- #


def test_only_the_first_chunk_of_a_table_run_keeps_its_header():
    hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |"),
        _hit("d1", f"{HEADER}\n| b | 2 |"),
        _hit("d1", f"{HEADER}\n| c | 3 |"),
    ]

    out = adapters_module._strip_repeated_table_headers(hits)

    assert out[0].content == f"{HEADER}\n| a | 1 |"
    assert out[1].content == "| b | 2 |"
    assert out[2].content == "| c | 3 |"


def test_first_table_chunk_keeps_its_header_after_an_intro_chunk():
    hits = [_hit("d1", "Intro paragraph."), _hit("d1", f"{HEADER}\n| a | 1 |")]

    out = adapters_module._strip_repeated_table_headers(hits)

    assert out[1].content == f"{HEADER}\n| a | 1 |"


def test_headers_are_not_stripped_across_documents():
    hits = [_hit("d1", f"{HEADER}\n| a | 1 |"), _hit("d2", f"{HEADER}\n| b | 2 |")]

    out = adapters_module._strip_repeated_table_headers(hits)

    assert out[1].content == f"{HEADER}\n| b | 2 |"


# --------------------------------------------------------------------------- #
# _complete_truncated_table, through the invoker
# --------------------------------------------------------------------------- #


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s-1", team_id="team-1"),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _client_returning(
    search_hits: list[VectorSearchHit], fetched: list[VectorSearchHit]
):
    calls: list[dict[str, Any]] = []

    class _FakeSearchClient:
        def __init__(self, agent: object) -> None:
            self._agent = agent

        async def search(self, **_kwargs: Any) -> list[VectorSearchHit]:
            return list(search_hits)

        async def get_document_chunks(self, **kwargs: Any) -> list[VectorSearchHit]:
            calls.append(kwargs)
            return list(fetched)

    return _FakeSearchClient, calls


async def _invoke(monkeypatch: pytest.MonkeyPatch, client_cls) -> Any:
    monkeypatch.setattr(adapters_module, "VectorSearchClient", client_cls)
    binding = _binding()
    invoker = adapters_module.FredKnowledgeSearchToolInvoker(
        binding=binding, settings=_FakeSettings()
    )
    return await invoker.invoke(
        ToolInvocationRequest(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            payload={"query": "what is the default of b?", "top_k": 2},
            context=binding.portable_context,
        )
    )


@pytest.mark.asyncio
async def test_truncated_table_is_refetched_whole_with_a_bounded_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the fetch is keyword-only and capped, and it must actually run."""
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0),
        _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=2),
    ]
    fetched = [
        _hit("d1", f"{HEADER}\n| {row} | {i} |", chunk_index=i)
        for i, row in enumerate("abc")
    ]
    client_cls, calls = _client_returning(search_hits, fetched)

    result = await _invoke(monkeypatch, client_cls)

    assert calls == [
        {"document_uid": "d1", "limit": adapters_module._TABLE_EXPANSION_MAX_CHUNKS}
    ]
    contents = [hit["content"] for hit in result.blocks[0].data["hits"]]
    assert contents == [f"{HEADER}\n| a | 0 |", "| b | 1 |", "| c | 2 |"]


@pytest.mark.asyncio
async def test_a_single_table_chunk_does_not_trigger_a_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0),
        _hit("d2", "plain prose", chunk_index=0),
    ]
    client_cls, calls = _client_returning(search_hits, [])

    await _invoke(monkeypatch, client_cls)

    assert calls == []


@pytest.mark.asyncio
async def test_a_failing_refetch_leaves_the_original_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0),
        _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=2),
    ]

    class _FailingClient:
        def __init__(self, agent: object) -> None:
            self._agent = agent

        async def search(self, **_kwargs: Any) -> list[VectorSearchHit]:
            return list(search_hits)

        async def get_document_chunks(self, **_kwargs: Any) -> list[VectorSearchHit]:
            raise RuntimeError("knowledge-flow is down")

    result = await _invoke(monkeypatch, _FailingClient)

    contents = [hit["content"] for hit in result.blocks[0].data["hits"]]
    assert contents == [f"{HEADER}\n| a | 1 |", "| c | 3 |"]


OTHER_HEADER = "| country | code |\n| --- | --- |"


def test_a_second_distinct_table_keeps_its_own_header():
    """Stripping on adjacency alone would reattribute these rows to the first table."""
    hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |"),
        _hit("d1", f"{OTHER_HEADER}\n| FR | 33 |"),
    ]

    out = adapters_module._strip_repeated_table_headers(hits)

    assert out[1].content == f"{OTHER_HEADER}\n| FR | 33 |"


@pytest.mark.asyncio
async def test_contiguous_table_chunks_are_not_refetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two adjacent chunks are a complete slice; there is nothing to complete."""
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=4),
        _hit("d1", f"{HEADER}\n| b | 2 |", chunk_index=5),
    ]
    client_cls, calls = _client_returning(search_hits, [])

    await _invoke(monkeypatch, client_cls)

    assert calls == []


@pytest.mark.asyncio
async def test_a_document_larger_than_the_cap_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A head-truncated refetch would drop the chunks that actually matched."""
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=60),
        _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=62),
    ]
    fetched = [
        _hit("d1", f"{HEADER}\n| r{i} | {i} |", chunk_index=i)
        for i in range(adapters_module._TABLE_EXPANSION_MAX_CHUNKS)
    ]
    client_cls, _ = _client_returning(search_hits, fetched)

    result = await _invoke(monkeypatch, client_cls)

    contents = [hit["content"] for hit in result.blocks[0].data["hits"]]
    assert contents == [f"{HEADER}\n| a | 1 |", "| c | 3 |"]


@pytest.mark.asyncio
async def test_refetched_chunks_keep_the_document_as_a_citable_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fetch carries no score of its own, so it inherits the document's best."""
    search_hits = [
        _hit("d2", "unrelated prose", chunk_index=0, score=0.8),
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0, score=0.9),
        _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=2, score=0.85),
    ]
    fetched = [
        _hit("d1", f"{HEADER}\n| {row} | {i} |", chunk_index=i, score=0.0)
        for i, row in enumerate("abc")
    ]
    client_cls, _ = _client_returning(search_hits, fetched)

    result = await _invoke(monkeypatch, client_cls)

    assert "d1" in {source.uid for source in result.sources}


@pytest.mark.asyncio
async def test_the_completed_document_keeps_its_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Appending the fetch at the end would demote the one document the fix serves."""
    search_hits = [
        _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0, score=0.95),
        _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=2, score=0.94),
        _hit("d2", "unrelated prose", chunk_index=0, score=0.5),
    ]
    fetched = [
        _hit("d1", f"{HEADER}\n| {row} | {i} |", chunk_index=i)
        for i, row in enumerate("abc")
    ]
    client_cls, _ = _client_returning(search_hits, fetched)

    result = await _invoke(monkeypatch, client_cls)

    assert [hit["uid"] for hit in result.blocks[0].data["hits"]] == [
        "d1",
        "d1",
        "d1",
        "d2",
    ]
