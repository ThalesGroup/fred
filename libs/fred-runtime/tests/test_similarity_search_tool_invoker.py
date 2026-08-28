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
"""
Built-in `knowledge.similarity_search` tool ref
(`FredKnowledgeSearchToolInvoker._invoke_similarity_search`, adapters.py).

Covers what the handler owns and the client below it does not: argument
extraction (including the nested-payload shape some model providers emit),
the required-targeting guard, and the source/content split - every hit is
citable here, unlike `knowledge.search`, because the caller named the targets.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_core.store.vector_search import (
    DATASET_POINTER_CHUNK_KIND,
    VectorSearchHit,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolInvocationRequest,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.support.builtins.catalog import TOOL_REF_SIMILARITY_SEARCH


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _RecordingSearchClient:
    """Stand-in for VectorSearchClient that records the kwargs it was called
    with, so the test can assert what reached Knowledge Flow."""

    last_call: dict[str, Any] = {}

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def similarity_search(self, **kwargs: Any) -> list[VectorSearchHit]:
        type(self).last_call = kwargs
        return [
            VectorSearchHit(
                uid="d1",
                title="Doc 1",
                content="alpha",
                score=0.9,
                type="document",
            ),
            # Weak relative to d1: knowledge.search would drop this from
            # sources, similarity_search must not.
            VectorSearchHit(
                uid="d2",
                title="Doc 2",
                content="beta",
                score=0.05,
                type="document",
            ),
            # Metadata, not content - never citable, whatever it scores.
            VectorSearchHit(
                uid="d3",
                title="Doc 3",
                content="dataset blurb",
                score=0.8,
                type="document",
                chunk_kind=DATASET_POINTER_CHUNK_KIND,
            ),
        ]


def _binding(**runtime_kwargs: Any) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1", team_id="team-1", **runtime_kwargs
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _invoker(monkeypatch: pytest.MonkeyPatch, **runtime_kwargs: Any) -> Any:
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _RecordingSearchClient)
    _RecordingSearchClient.last_call = {}
    binding = _binding(**runtime_kwargs)
    return adapters_module.FredKnowledgeSearchToolInvoker(
        binding=binding, settings=_FakeSettings()
    ), binding


async def _invoke(invoker: Any, binding: BoundRuntimeContext, payload: dict[str, Any]):
    return await invoker.invoke(
        ToolInvocationRequest(
            tool_ref=TOOL_REF_SIMILARITY_SEARCH,
            payload=payload,
            context=binding.portable_context,
        )
    )


@pytest.mark.asyncio
async def test_forwards_arguments_and_keeps_every_hit_citable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoker, binding = _invoker(monkeypatch)

    result = await _invoke(
        invoker,
        binding,
        {
            "anchor": "the service exposes a REST API",
            "document_uids": ["doc-a", "doc-b"],
            "top_k": 3,
            "rerank": False,
            "min_score": 0.2,
        },
    )

    assert _RecordingSearchClient.last_call == {
        "anchor": "the service exposes a REST API",
        "document_uids": ["doc-a", "doc-b"],
        "top_k": 3,
        "rerank": False,
        "min_score": 0.2,
    }

    assert result.blocks[0].data is not None
    assert result.blocks[0].data["anchor"] == "the service exposes a REST API"
    hits_payload = cast(list[dict[str, Any]], result.blocks[0].data["hits"])
    # LLM slice: citation/reasoning fields only, no operational fields.
    assert set(hits_payload[0]) <= {
        "uid",
        "title",
        "content",
        "file_name",
        "page",
        "section",
        "score",
    }
    # Targeting was explicit, so the low-scoring hit stays citable - but the
    # dataset pointer never is.
    assert [hit.uid for hit in result.sources] == ["d1", "d2"]


@pytest.mark.asyncio
async def test_applies_defaults_when_optional_arguments_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoker, binding = _invoker(monkeypatch)

    await _invoke(invoker, binding, {"anchor": "x", "document_uids": ["doc-a"]})

    assert _RecordingSearchClient.last_call["top_k"] == 10
    assert _RecordingSearchClient.last_call["rerank"] is True
    assert _RecordingSearchClient.last_call["min_score"] is None


@pytest.mark.asyncio
async def test_reads_arguments_from_a_nested_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoker, binding = _invoker(monkeypatch)

    await _invoke(
        invoker,
        binding,
        {"payload": {"anchor": "x", "document_uids": ["doc-a"], "top_k": 4}},
    )

    assert _RecordingSearchClient.last_call["anchor"] == "x"
    assert _RecordingSearchClient.last_call["document_uids"] == ["doc-a"]
    assert _RecordingSearchClient.last_call["top_k"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"document_uids": ["doc-a"]},
        {"anchor": "   ", "document_uids": ["doc-a"]},
        {"anchor": "x"},
        {"anchor": "x", "document_uids": []},
        {"anchor": "x", "document_uids": "doc-a"},
    ],
    ids=[
        "missing-anchor",
        "blank-anchor",
        "missing-uids",
        "empty-uids",
        "uids-not-a-list",
    ],
)
async def test_rejects_calls_without_an_anchor_and_a_target(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    invoker, binding = _invoker(monkeypatch)

    with pytest.raises(RuntimeError):
        await _invoke(invoker, binding, payload)

    assert _RecordingSearchClient.last_call == {}


@pytest.mark.asyncio
async def test_falls_back_to_default_top_k_on_a_nonsense_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoker, binding = _invoker(monkeypatch)

    await _invoke(
        invoker,
        binding,
        {"anchor": "x", "document_uids": ["doc-a"], "top_k": -1, "min_score": "high"},
    )

    assert _RecordingSearchClient.last_call["top_k"] == 10
    assert _RecordingSearchClient.last_call["min_score"] is None


@pytest.mark.asyncio
async def test_clamps_top_k_to_the_declared_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`SimilaritySearchToolArgs` declares 1-50 but nothing re-validates a
    model-emitted value between the handler and Knowledge Flow."""
    invoker, binding = _invoker(monkeypatch)

    await _invoke(
        invoker, binding, {"anchor": "x", "document_uids": ["doc-a"], "top_k": 5000}
    )

    assert _RecordingSearchClient.last_call["top_k"] == 50


@pytest.mark.asyncio
async def test_booleans_are_not_read_as_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`bool` is an `int` subclass: `min_score=True` would coerce to 1.0 and
    silently filter out every hit."""
    invoker, binding = _invoker(monkeypatch)

    await _invoke(
        invoker,
        binding,
        {
            "anchor": "x",
            "document_uids": ["doc-a"],
            "top_k": True,
            "min_score": True,
        },
    )

    assert _RecordingSearchClient.last_call["top_k"] == 10
    assert _RecordingSearchClient.last_call["min_score"] is None


@pytest.mark.asyncio
async def test_general_only_mode_skips_the_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naming target uids must not opt back into a corpus the user turned off."""
    invoker, binding = _invoker(monkeypatch, search_rag_scope="general_only")

    result = await _invoke(
        invoker, binding, {"anchor": "x", "document_uids": ["doc-a"]}
    )

    assert _RecordingSearchClient.last_call == {}
    assert result.sources == ()
    assert result.blocks[0].data is not None
    assert result.blocks[0].data["hits"] == []
