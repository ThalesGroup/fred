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
"""Every retrieval surface repairs table hits, not just the legacy one.

The fix first landed only on `knowledge.search`, while live agents call
`search_documents_using_vectorization` - served by `KfVectorSearchToolkit` or by
the `DocumentSearchPort` behind `document_access`. A shuffled table reaching the
model through either of those is the same bug, so these lock the wiring.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import fred_runtime.integrations.kf_vector_search.toolkit as toolkit_module
import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.common.structures import AgentSettingsLike
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import AgentTuning, MCPServerRef


class _FakeSettings:
    """Matches the AgentSettingsLike protocol."""

    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _FakeAgent:
    """Minimal shim matching what VectorSearchClient + the toolkit read."""

    def __init__(self) -> None:
        self.runtime_context = RuntimeContext(session_id="s-1", team_id="team-1")
        self.agent_settings: AgentSettingsLike = _FakeSettings()

    async def refresh_user_access_token(self) -> str:
        return "token"


HEADER = "| name | default |\n| --- | --- |"


def _hit(
    uid: str, content: str, *, chunk_index: int, score: float = 0.9
) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid,
        title=uid,
        content=content,
        score=score,
        type="document",
        chunk_index=chunk_index,
    )


# A table cut short by top_k: chunks 0 and 2 came back, chunk 1 did not.
TRUNCATED = [
    _hit("d1", f"{HEADER}\n| a | 1 |", chunk_index=0),
    _hit("d1", f"{HEADER}\n| c | 3 |", chunk_index=2),
]
WHOLE = [
    _hit("d1", f"{HEADER}\n| {row} | {i} |", chunk_index=i)
    for i, row in enumerate("abc")
]


class _FakeClient:
    """Stands in for VectorSearchClient on both surfaces."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        self.fetched: list[dict[str, Any]] = []

    async def search(self, **_kwargs: Any) -> list[VectorSearchHit]:
        return list(TRUNCATED)

    async def get_document_chunks(self, **kwargs: Any) -> list[VectorSearchHit]:
        self.fetched.append(kwargs)
        return list(WHOLE)


def _assert_repaired(contents: list[str]) -> None:
    # completed to three rows, in index order, with the repeated header dropped
    assert contents == [f"{HEADER}\n| a | 0 |", "| b | 1 |", "| c | 2 |"]


@pytest.mark.asyncio
async def test_toolkit_repairs_table_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient()
    monkeypatch.setattr(toolkit_module, "VectorSearchClient", lambda **_kw: client)

    tools = toolkit_module.KfVectorSearchToolkit(agent=_FakeAgent()).tools()
    result = await tools[0].ainvoke(
        {"question": "what is the default of b?", "top_k": 2}
    )

    assert client.fetched == [{"document_uid": "d1", "limit": 40}]
    _assert_repaired([hit["content"] for hit in result.blocks[0].data["hits"]])


@pytest.mark.asyncio
async def test_document_search_port_repairs_table_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    monkeypatch.setattr(adapters_module, "VectorSearchClient", lambda **_kw: client)

    from tests.test_knowledge_search_tool_invoker_sources import _binding, _FakeSettings

    adapter = adapters_module.DocumentSearchAdapter(
        binding=_binding(), settings=_FakeSettings()
    )
    result = await adapter.search("what is the default of b?", top_k=2)

    assert client.fetched == [{"document_uid": "d1", "limit": 40}]
    _assert_repaired([hit.content for hit in result.hits])
