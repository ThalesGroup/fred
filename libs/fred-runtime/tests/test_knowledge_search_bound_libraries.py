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
Server-side library binding of the builtin `knowledge.search` tool.

An agent instance bound to libraries (a capability's `document_scope` chat
control carrying `bound_library_ids`) keeps that scope whatever the client
sends: the turn's selection may only narrow it, and a selection wholly outside
it finds nothing rather than searching unfiltered. The legacy tree
port applies the same "empty scope finds nothing" rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.app.agent_app import _instance_bound_library_ids
from fred_runtime.capabilities import CapabilityRegistry, resolve_bound_library_ids
from fred_runtime.runtime_context import (
    RuntimeConfig,
    get_runtime_context,
    set_runtime_context,
)
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
    StoredCapabilityConfig,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolInvocationRequest,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    DocumentScopeControlParams,
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
    MCPServerRef,
)
from fred_sdk.contracts.runtime import DocumentTreeResult
from fred_sdk.support.builtins.catalog import TOOL_REF_KNOWLEDGE_SEARCH
from pydantic import BaseModel


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _RecordingSearchClient:
    """Stand-in for VectorSearchClient that records every search call."""

    calls: list[dict[str, Any]] = []

    def __init__(self, agent: object) -> None:
        del agent

    async def search(self, **kwargs: Any) -> list[VectorSearchHit]:
        type(self).calls.append(kwargs)
        return [
            VectorSearchHit(
                uid="d1", title="Doc 1", content="alpha", score=0.9, type="document"
            )
        ]

    async def get_document_chunks(self, **_kwargs: object) -> list[VectorSearchHit]:
        return []


def _binding(
    selected_libraries: list[str] | None = None,
    selected_documents: list[str] | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1",
            team_id="team-1",
            selected_document_libraries_ids=selected_libraries,
            selected_document_uids=selected_documents,
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bound: list[str] | None,
    selected: list[str] | None,
    documents: list[str] | None = None,
):
    _RecordingSearchClient.calls = []
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _RecordingSearchClient)
    binding = _binding(selected, documents)
    invoker = adapters_module.FredKnowledgeSearchToolInvoker(
        binding=binding, settings=_FakeSettings(), bound_library_ids=bound
    )
    return await invoker.invoke(
        ToolInvocationRequest(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            payload={"query": "what is alpha?"},
            context=binding.portable_context,
        )
    )


@pytest.mark.asyncio
async def test_bound_libraries_apply_without_any_client_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An API run (no chat UI) sends no library selection at all.
    await _search(monkeypatch, bound=["lib-a"], selected=None)

    assert [
        call["document_library_tags_ids"] for call in _RecordingSearchClient.calls
    ] == [["lib-a"]]


@pytest.mark.asyncio
async def test_selection_narrows_bound_libraries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _search(monkeypatch, bound=["lib-a", "lib-b"], selected=["lib-b", "lib-x"])

    assert [
        call["document_library_tags_ids"] for call in _RecordingSearchClient.calls
    ] == [["lib-b"]]


@pytest.mark.asyncio
async def test_selection_outside_bound_libraries_finds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _search(monkeypatch, bound=["lib-a"], selected=["lib-x"])

    # Never an unfiltered search: the vector client drops an empty filter.
    assert _RecordingSearchClient.calls == []
    assert result.sources == ()


@pytest.mark.asyncio
async def test_selection_outside_bound_libraries_still_searches_picked_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Libraries and documents union in Knowledge Flow: an empty library arm
    # leaves the picked document to search.
    await _search(monkeypatch, bound=["lib-a"], selected=["lib-x"], documents=["doc-d"])

    assert [
        (call["document_library_tags_ids"], call["document_uids"])
        for call in _RecordingSearchClient.calls
    ] == [([], ["doc-d"])]


@pytest.mark.asyncio
async def test_unbound_agent_keeps_the_client_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _search(monkeypatch, bound=None, selected=["lib-x"])

    assert [
        call["document_library_tags_ids"] for call in _RecordingSearchClient.calls
    ] == [["lib-x"]]


class _RecordingTreeClient:
    """Stand-in for KfDocumentClient's tree call."""

    calls: list[dict[str, Any]] = []

    def __init__(self, agent: object) -> None:
        del agent

    async def tree(self, **kwargs: Any) -> DocumentTreeResult:
        type(self).calls.append(kwargs)
        return DocumentTreeResult(tree="Sales/", truncated=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_libraries,capability_libraries",
    [
        # The capability's bound libraries miss everything the client selected.
        (["lib-x"], ["lib-a"]),
        # The capability's own turn-option narrowing already came out empty.
        (None, []),
    ],
)
async def test_legacy_tree_finds_nothing_for_an_empty_scope(
    monkeypatch: pytest.MonkeyPatch,
    session_libraries: list[str] | None,
    capability_libraries: list[str],
) -> None:
    _RecordingSearchClient.calls = []
    _RecordingTreeClient.calls = []
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _RecordingSearchClient)
    monkeypatch.setattr(adapters_module, "KfDocumentClient", _RecordingTreeClient)
    binding = _binding(session_libraries)
    tree = adapters_module.DocumentTreeAdapter(
        binding=binding, settings=_FakeSettings()
    )

    listing = await tree.tree(library_tag_ids=capability_libraries)

    # An empty filter would reach Knowledge Flow as no filter at all.
    assert _RecordingSearchClient.calls == []
    assert _RecordingTreeClient.calls == []
    assert listing.tree == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_libraries,capability_libraries",
    [
        # The capability's bound libraries miss everything the client selected.
        (["lib-x"], ["lib-a"]),
        # The capability's own narrowing came out empty: the session's
        # libraries must not come back in.
        (["lib-x"], []),
    ],
)
async def test_legacy_tree_keeps_picked_documents_for_an_empty_library_scope(
    monkeypatch: pytest.MonkeyPatch,
    session_libraries: list[str],
    capability_libraries: list[str],
) -> None:
    _RecordingSearchClient.calls = []
    _RecordingTreeClient.calls = []
    monkeypatch.setattr(adapters_module, "VectorSearchClient", _RecordingSearchClient)
    monkeypatch.setattr(adapters_module, "KfDocumentClient", _RecordingTreeClient)
    binding = _binding(session_libraries, ["doc-d"])
    tree = adapters_module.DocumentTreeAdapter(
        binding=binding, settings=_FakeSettings()
    )

    await tree.tree(library_tag_ids=capability_libraries)

    # Libraries and documents union in Knowledge Flow: the picked document
    # is still searched and listed, and no library is.
    assert _RecordingSearchClient.calls == []
    assert [
        (call["tag_ids"], call["document_uids"]) for call in _RecordingTreeClient.calls
    ] == [([], ["doc-d"])]


class _ScopeConfig(BaseModel):
    library_tag_ids: list[str] = []


class _BindingCapability(AgentCapability[_ScopeConfig, _ScopeConfig, EmptyModel]):
    """Binds its configured libraries through the stock `document_scope` control."""

    manifest = CapabilityManifest(
        id="binding_probe",
        version="1.0.0",
        name="cap.binding_probe.name",
        description="cap.binding_probe.description",
        icon="Build",
    )
    ConfigModel = _ScopeConfig

    def chat_controls(self, config: _ScopeConfig) -> list[ChatControlSpec]:
        return [
            ChatControlSpec(
                widget="document_scope",
                params=DocumentScopeControlParams(
                    libraries=True,
                    documents=False,
                    bound_library_ids=config.library_tag_ids or None,
                ),
            )
        ]


def _envelope(library_tag_ids: list[str]) -> StoredCapabilityConfig:
    return StoredCapabilityConfig(
        schema_version="1.0.0", config={"library_tag_ids": library_tag_ids}
    )


def test_resolve_bound_library_ids_reads_the_stored_config() -> None:
    registry = CapabilityRegistry()
    registry.register(_BindingCapability())

    assert resolve_bound_library_ids(
        registry,
        capability_ids=["binding_probe"],
        capability_config={"binding_probe": _envelope(["lib-a", "lib-b"])},
    ) == ["lib-a", "lib-b"]
    # No stored config: the capability's defaults bind nothing.
    assert (
        resolve_bound_library_ids(
            registry, capability_ids=["binding_probe"], capability_config={}
        )
        is None
    )


class _Input(BaseModel):
    message: str = ""


class _IncludedCapabilityGraphAgent(GraphAgentDefinition):
    """A graph agent without free selection that includes `binding_probe`."""

    agent_id: str = "test.graph_included_binding"
    role: str = "test"
    description: str = "test"
    default_mcp_servers: tuple[MCPServerRef, ...] = (MCPServerRef(id="binding_probe"),)

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="Input",
            entry_node="n",
            nodes=(GraphNodeDefinition(node_id="n", title="N"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _Input

    def state_model(self) -> type[BaseModel]:
        return _Input

    def output_model(self) -> type[BaseModel]:
        return _Input

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        return _Input()

    def node_handlers(self) -> Mapping[str, object]:
        return {}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _Input()


@pytest.fixture
def _runtime_context():
    try:
        previous = get_runtime_context()
    except RuntimeError:
        previous = None
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    yield
    set_runtime_context(previous)


@pytest.mark.usefixtures("_runtime_context")
def test_graph_agent_binding_comes_from_its_included_capability_config() -> None:
    definition = _IncludedCapabilityGraphAgent()
    assert definition.supports_capabilities is False
    registry = CapabilityRegistry()
    registry.register(_BindingCapability())
    # The saved selection is ignored for an agent without free selection; the
    # included capability stays active and its stored config is honoured.
    tuning = AgentTuning(
        role=definition.role,
        description=definition.description,
        selected_capability_ids=[],
        capability_config={"binding_probe": _envelope(["lib-a"])},
    )

    assert _instance_bound_library_ids(registry, tuning, definition) == ["lib-a"]
