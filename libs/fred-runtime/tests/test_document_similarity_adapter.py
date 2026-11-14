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
from unittest.mock import MagicMock
from uuid import UUID

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import httpx
import pytest
import pytest_asyncio
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeTimeouts,
    set_runtime_context,
)
from fred_runtime.runtime_context import RuntimeContext as PodRuntimeContext
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_sdk.contracts.context import (
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import (
    DocumentPortCallError,
    DocumentScopeRefusedError,
)
from weaver_fixtures import SPACE_ID, active_turn, local_binding

pytestmark = pytest.mark.asyncio
DOC_A, DOC_ELSEWHERE = [str(UUID(int=i)) for i in (101, 999)]


@pytest_asyncio.fixture(autouse=True)
async def admitted_turn(empty_runtime_context):
    set_runtime_context(
        PodRuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.invalid",
                timeouts=RuntimeTimeouts(similarity_read=37.0),
            )
        )
    )
    with active_turn("agent-1", session="s-1"):
        yield


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

    async def search(self, **kwargs: Any) -> list[VectorSearchHit]:
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
    binding = local_binding(
        "agent-1",
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
        "anchor text", document_uids=[DOC_A], top_k=5, rerank=False, min_score=0.2
    )

    assert _RecordingClient.last_call == {
        "question": "anchor text",
        "document_context": DocumentAccessContext(
            space_id=UUID(SPACE_ID),
            authorized_space_ids=(UUID(SPACE_ID),),
            document_scope=DocumentScope.from_ids(document_ids=[DOC_A]),
        ),
        "top_k": 5,
        "rerank": False,
        "min_score": 0.2,
        "read_timeout": 37.0,
        "transient_retry": True,
    }
    assert [hit.uid for hit in result.hits] == ["d1"]


async def test_bounds_model_named_uids_by_the_session_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model asked for two documents; only one is in this conversation."""
    adapter = _adapter(monkeypatch, selected_document_uids=[DOC_A])

    await adapter.find_similar("x", document_uids=[DOC_A, DOC_ELSEWHERE])

    assert _RecordingClient.last_call is not None
    assert _RecordingClient.last_call[
        "document_context"
    ].document_scope == DocumentScope.from_ids(document_ids=[DOC_A])


async def test_every_named_uid_outside_the_session_scope_is_refused_not_emptied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two things must not happen when the intersection is empty: calling
    Knowledge Flow with an empty target list (which reads downstream as 'no
    targeting'), and returning no hits (which the model cannot tell apart from
    a genuine no-match, and would report as 'nothing resembles this')."""
    adapter = _adapter(monkeypatch, selected_document_uids=[DOC_A])

    with pytest.raises(DocumentScopeRefusedError) as excinfo:
        await adapter.find_similar("x", document_uids=[DOC_ELSEWHERE])

    assert excinfo.value.requested_uids == (DOC_ELSEWHERE,)
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

    result = await adapter.find_similar("x", document_uids=[DOC_A])

    assert result.hits == ()
    assert _RecordingClient.last_call is None


async def test_transport_failure_is_mapped_to_the_sdk_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So the capability can render an `is_error` result without importing httpx."""
    adapter = _adapter(monkeypatch)
    _RecordingClient.error = httpx.ConnectError("dropped")

    with pytest.raises(DocumentPortCallError):
        await adapter.find_similar("x", document_uids=[DOC_A])


async def test_wrapped_authority_loss_is_not_mapped_to_a_document_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch)
    stop = AuthorityLostError()
    try:
        raise stop
    except AuthorityLostError as exc:
        try:
            raise httpx.HTTPError("transport wrapper") from exc
        except httpx.HTTPError as wrapper:
            _RecordingClient.error = wrapper

    with pytest.raises(AuthorityLostError) as raised:
        await adapter.find_similar("x", document_uids=[DOC_A])

    assert raised.value is stop


@pytest.mark.parametrize("selected", [None, [DOC_A]])
async def test_invalid_identifier_does_not_discard_valid_targets(monkeypatch, selected):
    adapter = _adapter(monkeypatch, selected_document_uids=selected)
    debug = MagicMock()
    monkeypatch.setattr(adapters_module.logger, "debug", debug)

    result = await adapter.find_similar(
        "private anchor", document_uids=["not-a-uuid", DOC_A]
    )

    assert [hit.uid for hit in result.hits] == ["d1"]
    assert _RecordingClient.last_call is not None
    assert _RecordingClient.last_call[
        "document_context"
    ].document_scope == DocumentScope.from_ids(document_ids=[DOC_A])
    debug.assert_called_once_with(
        "Ignoring invalid document similarity identifier: %r", "not-a-uuid"
    )


@pytest.mark.parametrize("selected", [None, [DOC_A]])
async def test_only_invalid_identifiers_never_reach_knowledge_flow(
    monkeypatch, selected
):
    adapter = _adapter(monkeypatch, selected_document_uids=selected)

    result = await adapter.find_similar(
        "private anchor", document_uids=["not-a-uuid", ""]
    )

    assert result.hits == ()
    assert _RecordingClient.last_call is None


async def test_invalid_identifier_does_not_hide_valid_scope_refusal(monkeypatch):
    adapter = _adapter(monkeypatch, selected_document_uids=[DOC_A])

    with pytest.raises(DocumentScopeRefusedError):
        await adapter.find_similar(
            "private anchor", document_uids=["not-a-uuid", DOC_ELSEWHERE]
        )

    assert _RecordingClient.last_call is None
