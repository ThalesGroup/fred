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
`FredKnowledgeSearchToolInvoker._invoke_similarity_search` (TOOL_REF_SIMILARITY_SEARCH,
adapters.py) delegates to `DocumentSimilarityAdapter` — the same
`RuntimeServices.document_similarity` port the `document_similarity` capability
uses (RUNTIME-EXECUTION-CONTRACT.md §8.60/§8.63) — rather than calling
`VectorSearchClient` directly. Covers the two behaviours that delegation adds:
citable-source filtering and conversation-scope enforcement.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

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
from fred_sdk.support.builtins.catalog import TOOL_REF_SIMILARITY_SEARCH


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _FakeSimilarityClient:
    """Stand-in for VectorSearchClient — one strong hit, one hit that's noise
    relative to it, so a real score-ratio filter would (wrongly) drop it."""

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def similarity_search(self, **kwargs: Any) -> list[VectorSearchHit]:
        return [
            VectorSearchHit(
                uid="d1", title="Doc 1", content="alpha", score=0.5, type="document"
            ),
            VectorSearchHit(
                uid="d2", title="Doc 2", content="beta", score=0.05, type="document"
            ),
        ]


def _binding(selected_document_uids: list[str] | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1",
            team_id="team-1",
            selected_document_uids=selected_document_uids,
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest.mark.asyncio
async def test_similarity_search_keeps_both_hits_unfiltered_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _FakeSimilarityClient)
    invoker = adapters_module.FredKnowledgeSearchToolInvoker(
        binding=_binding(), settings=_FakeSettings()
    )

    result = await invoker.invoke(
        ToolInvocationRequest(
            tool_ref=TOOL_REF_SIMILARITY_SEARCH,
            payload={"anchor": "alpha passage", "document_uids": ["d1", "d2"]},
            context=_binding().portable_context,
        )
    )

    # min_score_ratio=0.0 (targeted comparison, not corpus search): the weak
    # hit stays a source, unlike knowledge.search's default relative cutoff.
    assert result.blocks[0].data is not None
    hits_payload = cast(list[dict[str, Any]], result.blocks[0].data["hits"])
    assert {hit.get("content") for hit in hits_payload} == {"alpha", "beta"}
    assert {hit.uid for hit in result.sources} == {"d1", "d2"}


@pytest.mark.asyncio
async def test_similarity_search_refuses_document_uids_outside_conversation_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _FakeSimilarityClient)
    invoker = adapters_module.FredKnowledgeSearchToolInvoker(
        binding=_binding(selected_document_uids=["only-this-doc"]),
        settings=_FakeSettings(),
    )

    with pytest.raises(
        RuntimeError, match="none of the requested documents are in scope"
    ):
        await invoker.invoke(
            ToolInvocationRequest(
                tool_ref=TOOL_REF_SIMILARITY_SEARCH,
                payload={"anchor": "alpha passage", "document_uids": ["d1"]},
                context=_binding().portable_context,
            )
        )
