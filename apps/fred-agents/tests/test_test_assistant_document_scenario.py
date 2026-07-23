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
End-to-end proof of the Graph <-> AgentCapability bridge
(NOTES-GRAPH-CAPABILITY-BRIDGE.md Phase 6) on a real, user-recognizable
agent: `test_assistant`'s "document" scenario.

Why this file exists:
- Phases 1-5 (`libs/fred-runtime`) proved every link of the bridge in
  isolation (capability contract, assembly, capability-vs-graph adapter,
  wiring). This file drives the actual `TestAssistantGraphAgent` graph
  through a real `GraphRuntime`, constructed with a real
  `CapabilityAgentBlock` assembled from a real `CapabilityRegistry` — the
  same seams a production pod uses — proving search -> HITL -> branch
  survives the full chain on a genuine end-user-shaped agent, not just an
  internal test fixture.
- `document_access` is selected via `tuning.selected_capability_ids`
  (a managed-instance concept), never declared on `TestAssistantGraphAgent`
  itself — mirrored here by building the capability block directly, the way
  `agent_app.py` would for a real managed instance.

Offline only: `_FakeDocumentSearchPort` stands in for the real Knowledge Flow
port; no live backend, pod, or docker is involved.
"""

from __future__ import annotations

import pytest
from fred_agents.test_assistant.graph_agent import TestAssistantGraphAgent
from fred_agents.test_assistant.graph_state import TestInput
from fred_core.store import VectorSearchHit
from fred_runtime.capabilities import (
    CapabilityRegistry,
    build_capability_agent_block,
    build_capability_contexts,
)
from fred_runtime.capabilities.document_access import DocumentAccessCapability
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_sdk.contracts.capability import CapabilityIdentity
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    DocumentSearchPort,
    DocumentSearchResult,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
)


class _FakeDocumentSearchPort(DocumentSearchPort):
    """Stands in for the real Knowledge Flow port — one deterministic hit."""

    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids=None,
        document_uids=None,
        search_policy=None,
        attachments_only: bool = False,
    ) -> DocumentSearchResult:
        return DocumentSearchResult(
            hits=(
                VectorSearchHit(
                    uid="doc-fred-1",
                    title="Fred Overview",
                    content="Fred is Thales's agentic AI platform.",
                    score=0.95,
                ),
            )
        )


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s1", user_id="u1", team_id="t1"),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="c1",
            actor="u1",
            tenant="t1",
            environment=PortableEnvironment.DEV,
            session_id="s1",
            user_id="u1",
            team_id="t1",
        ),
    )


def _document_access_capability_block(services: RuntimeServices):
    """Assemble a real `CapabilityAgentBlock` the way `agent_app.py` would
    for a managed instance with `tuning.selected_capability_ids =
    ["document_access"]` — never declared on `TestAssistantGraphAgent`."""

    registry = CapabilityRegistry()
    registry.register(DocumentAccessCapability())
    contexts = build_capability_contexts(
        registry,
        selected_capability_ids=["document_access"],
        capability_config={},
        identity=CapabilityIdentity(user_id="u1", session_id="s1", team_id="t1"),
        services=services,
    )
    return build_capability_agent_block(registry, contexts)


@pytest.mark.asyncio
async def test_document_scenario_search_hitl_confirm_survives_full_bridge() -> None:
    """search_documents_using_vectorization -> HITL confirm -> branch, through
    the real GraphRuntime/CapabilityAgentBlock/adapter chain (Phases 2-5)."""

    services = RuntimeServices(document_search=_FakeDocumentSearchPort())
    block = _document_access_capability_block(services)
    runtime = GraphRuntime(
        definition=TestAssistantGraphAgent(), services=services, capability_block=block
    )
    runtime.bind(_binding())
    executor = await runtime.get_executor()

    first_turn = [
        event
        async for event in executor.stream(
            TestInput(message="document what is fred"),
            ExecutionConfig(session_id="s1"),
        )
    ]
    awaiting = next(e for e in first_turn if isinstance(e, AwaitingHumanRuntimeEvent))
    assert awaiting.request.stage == "test_document_confirm"
    assert {c.id for c in awaiting.request.choices} == {"confirm", "discard"}

    resumed_turn = [
        event
        async for event in executor.stream(
            TestInput(message="document"),
            ExecutionConfig(session_id="s1", resume_payload={"choice_id": "confirm"}),
        )
    ]
    final = next(e for e in resumed_turn if isinstance(e, FinalRuntimeEvent))
    assert "Fred Overview" in final.content
    assert final.sources[0].uid == "doc-fred-1"


@pytest.mark.asyncio
async def test_document_scenario_without_capability_selected_degrades_gracefully() -> (
    None
):
    """No capability block at all (nobody selected `document_access` on this
    instance) -> invoke_runtime_tool raises -> the node degrades to a helpful
    message instead of crashing."""

    runtime = GraphRuntime(
        definition=TestAssistantGraphAgent(), services=RuntimeServices()
    )
    runtime.bind(_binding())
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            TestInput(message="document what is fred"),
            ExecutionConfig(session_id="s2"),
        )
    ]
    final = next(e for e in events if isinstance(e, FinalRuntimeEvent))
    assert "Document access" in final.content
    assert "capability" in final.content.lower()
