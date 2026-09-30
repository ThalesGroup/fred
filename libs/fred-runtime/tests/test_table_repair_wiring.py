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
"""Verify native document search repairs truncated table hits before returning them."""

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
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef


class _FakeSettings:
    """Matches the AgentSettingsLike protocol."""

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
    """Stands in for VectorSearchClient in the document-search adapter."""

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
async def test_document_search_port_repairs_table_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    monkeypatch.setattr(adapters_module, "VectorSearchClient", lambda **_kw: client)

    adapter = adapters_module.DocumentSearchAdapter(
        binding=_binding(), settings=_FakeSettings()
    )
    result = await adapter.search("what is the default of b?", top_k=2)

    assert client.fetched == [{"document_uid": "d1", "limit": 40}]
    _assert_repaired([hit.content for hit in result.hits])
