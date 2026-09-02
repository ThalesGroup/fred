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

"""`DocumentSimilarityAdapter` - the session-binding scope seam.

This adapter carries a weight its `DocumentSearchAdapter` sibling does not: the
document uids it receives come from the MODEL, on the call, not from the
capability's stored config. So this is the only place standing between an
LLM-named uid and a document the user never put in this conversation. These
cases pin that, plus the two ways an untargeted Knowledge Flow call could
otherwise sneak out.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import httpx
import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import (
    DocumentPortCallError,
    DocumentScopeRefusedError,
)

pytestmark = pytest.mark.asyncio


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _RecordingClient:
    """Stand-in for VectorSearchClient, recording what reached Knowledge Flow."""

    last_call: dict[str, Any] | None = None
    error: Exception | None = None

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def similarity_search(self, **kwargs: Any) -> list[VectorSearchHit]:
        type(self).last_call = kwargs
        error = type(self).error
        if error is not None:
            raise error
        return [
            VectorSearchHit(
                uid="d1", title="Doc 1", content="alpha", score=0.9, type="document"
            )
        ]


def _adapter(monkeypatch: pytest.MonkeyPatch, **runtime_kwargs: Any):
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _RecordingClient)
    _RecordingClient.last_call = None
    _RecordingClient.error = None
    binding = BoundRuntimeContext(
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
    return adapters_module.DocumentSimilarityAdapter(
        binding=binding, settings=_FakeSettings()
    )


async def test_forwards_a_targeted_call_and_returns_typed_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch)

    result = await adapter.find_similar(
        "anchor text", document_uids=["doc-a"], top_k=5, rerank=False, min_score=0.2
    )

    assert _RecordingClient.last_call == {
        "anchor": "anchor text",
        "document_uids": ["doc-a"],
        "top_k": 5,
        "rerank": False,
        "min_score": 0.2,
    }
    assert [hit.uid for hit in result.hits] == ["d1"]


async def test_bounds_model_named_uids_by_the_session_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model asked for two documents; only one is in this conversation."""
    adapter = _adapter(monkeypatch, selected_document_uids=["doc-a"])

    await adapter.find_similar("x", document_uids=["doc-a", "doc-elsewhere"])

    assert _RecordingClient.last_call is not None
    assert _RecordingClient.last_call["document_uids"] == ["doc-a"]


async def test_every_named_uid_outside_the_session_scope_is_refused_not_emptied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two things must not happen when the intersection is empty: calling
    Knowledge Flow with an empty target list (which reads downstream as 'no
    targeting'), and returning no hits (which the model cannot tell apart from
    a genuine no-match, and would report as 'nothing resembles this')."""
    adapter = _adapter(monkeypatch, selected_document_uids=["doc-a"])

    with pytest.raises(DocumentScopeRefusedError) as excinfo:
        await adapter.find_similar("x", document_uids=["doc-elsewhere"])

    assert excinfo.value.requested_uids == ("doc-elsewhere",)
    assert _RecordingClient.last_call is None


async def test_an_empty_target_never_reaches_knowledge_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch)

    result = await adapter.find_similar("x", document_uids=[])

    assert result.hits == ()
    assert _RecordingClient.last_call is None


async def test_general_only_mode_skips_the_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corpus retrieval turned off for the turn is off for every corpus tool;
    naming target uids does not opt back in."""
    adapter = _adapter(monkeypatch, search_rag_scope="general_only")

    result = await adapter.find_similar("x", document_uids=["doc-a"])

    assert result.hits == ()
    assert _RecordingClient.last_call is None


async def test_transport_failure_is_mapped_to_the_sdk_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So the capability can render an `is_error` result without importing httpx."""
    adapter = _adapter(monkeypatch)
    _RecordingClient.error = httpx.ConnectError("dropped")

    with pytest.raises(DocumentPortCallError):
        await adapter.find_similar("x", document_uids=["doc-a"])
