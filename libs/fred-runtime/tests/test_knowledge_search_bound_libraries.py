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
Library binding resolution for stored capability configuration.

The builtin `knowledge.search` carries Weaver folder/document selections;
its corpus search is covered by test_document_search_source_ceilings.py.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
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
)
from fred_sdk.contracts.models import (
    AgentTuning,
    DocumentScopeControlParams,
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
    MCPServerRef,
)
from pydantic import BaseModel


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
