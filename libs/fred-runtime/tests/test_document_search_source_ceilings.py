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
"""The agent's document sources bound the per-turn RAG scope, never widen it."""

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
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef, RagScopeName


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _FakeClient:
    def __init__(self, *, agent: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search(self, **kwargs: Any) -> list[VectorSearchHit]:
        self.calls.append(kwargs)
        return []

    async def get_document_chunks(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


def _adapter(
    monkeypatch: pytest.MonkeyPatch, rag_scope: str
) -> tuple[adapters_module.DocumentSearchAdapter, list[_FakeClient]]:
    clients: list[_FakeClient] = []

    def _factory(*, agent: Any) -> _FakeClient:
        client = _FakeClient(agent=agent)
        clients.append(client)
        return client

    monkeypatch.setattr(adapters_module, "VectorSearchClient", _factory)
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1",
            team_id="team-1",
            search_rag_scope=cast(RagScopeName, rag_scope),
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )
    adapter = adapters_module.DocumentSearchAdapter(
        binding=binding,
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    return adapter, clients


# (rag_scope, include_attachments, include_team_documents) -> flags sent, or
# None when Knowledge Flow must not be called at all.
CASES = [
    ("hybrid", True, True, (True, True)),
    ("hybrid", True, False, (True, False)),
    ("hybrid", False, True, (False, True)),
    ("corpus_only", True, True, (True, True)),
    ("corpus_only", False, True, (False, True)),
    ("corpus_only", True, False, (True, False)),
    ("general_only", True, True, None),
    ("general_only", True, False, None),
    ("general_only", False, True, None),
    ("hybrid", False, False, None),
    ("corpus_only", False, False, None),
    ("general_only", False, False, None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("rag_scope,attachments,team_documents,expected", CASES)
async def test_sources_bound_the_turn_scope(
    monkeypatch: pytest.MonkeyPatch,
    rag_scope: str,
    attachments: bool,
    team_documents: bool,
    expected: tuple[bool, bool] | None,
) -> None:
    adapter, clients = _adapter(monkeypatch, rag_scope)

    result = await adapter.search(
        "q",
        include_attachments=attachments,
        include_team_documents=team_documents,
    )

    calls = clients[0].calls
    if expected is None:
        assert result.hits == ()
        assert calls == []
        return
    assert (calls[0]["include_session_scope"], calls[0]["include_corpus_scope"]) == (
        expected
    )


@pytest.mark.asyncio
async def test_removed_attachments_only_keyword_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, clients = _adapter(monkeypatch, "hybrid")
    legacy_kwargs: dict[str, Any] = {"attachments_only": True}
    with pytest.raises(TypeError, match="attachments_only"):
        await adapter.search("q", **legacy_kwargs)
    assert clients[0].calls == []


@pytest.mark.parametrize("scope", ["corpus_only", "hybrid"])
@pytest.mark.parametrize(
    "session,corpus", [(True, False), (False, True), (False, False)]
)
def test_explicit_turn_scope_still_narrows_document_sources(
    scope: str, session: bool, corpus: bool
) -> None:
    context = RuntimeContext(
        search_rag_scope=cast(RagScopeName, scope),
        include_session_scope=session,
        include_corpus_scope=corpus,
    )
    assert adapters_module.get_vector_search_scopes(context) == (session, corpus)
