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
Sources filtering for the legacy built-in `knowledge.search` tool ref
(`FredKnowledgeSearchToolInvoker._invoke_knowledge_search`, adapters.py) —
same fix as `document_access` and `KfVectorSearchToolkit`, applied here for
the third and last place that builds a chat "Sources" panel from raw hits
(RAG-DATASET-DISCOVERY-RFC.md §7).
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
from fred_sdk.support.builtins.catalog import TOOL_REF_KNOWLEDGE_SEARCH


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _FakeSearchClientWithNoise:
    """Stand-in for VectorSearchClient — one strong hit, one hit that's noise
    relative to it."""

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def search(self, **kwargs: Any) -> list[VectorSearchHit]:
        return [
            VectorSearchHit(
                uid="d1", title="Doc 1", content="alpha", score=0.5, type="document"
            ),
            VectorSearchHit(
                uid="d2", title="Doc 2", content="beta", score=0.05, type="document"
            ),
        ]


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


@pytest.mark.asyncio
async def test_low_relevance_hit_excluded_from_knowledge_search_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapters_module, "VectorSearchClient", _FakeSearchClientWithNoise
    )
    binding = _binding()
    invoker = adapters_module.FredKnowledgeSearchToolInvoker(
        binding=binding, settings=_FakeSettings()
    )

    result = await invoker.invoke(
        ToolInvocationRequest(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            payload={"query": "what is alpha?", "top_k": 8},
            context=binding.portable_context,
        )
    )

    # The model still sees both hits (blocks carry the full JSON hit list).
    assert result.blocks[0].data is not None
    hits_payload = cast(list[dict[str, Any]], result.blocks[0].data["hits"])
    assert any(hit.get("content") == "beta" for hit in hits_payload)
    # Only the strong hit clears the default 0.5 score ratio.
    assert [hit.uid for hit in result.sources] == ["d1"]
