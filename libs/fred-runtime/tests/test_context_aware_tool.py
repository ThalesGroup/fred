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

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, List

import pytest
from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIEvent
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeContext as GlobalRuntimeContext,
    set_runtime_context,
)
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from langchain_core.tools import ArgsSchema, BaseTool
from pydantic import BaseModel


class _SearchArgs(BaseModel):
    question: str
    document_library_tags_ids: list[str] | None = None
    document_uids: list[str] | None = None
    session_id: str | None = None
    owner_filter: str | None = None
    team_id: str | None = None
    include_session_scope: bool | None = None
    include_corpus_scope: bool | None = None


class _FakeSearchTool(BaseTool):
    name: str = "fake.search"
    description: str = "Search tool used to validate context injection."
    args_schema: ArgsSchema | None = _SearchArgs

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "ok"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return "ok"


class _FakeAgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


def test_context_aware_tool_injects_document_filters_for_mcp_search_tools() -> None:
    runtime_context = RuntimeContext(
        session_id="session-1",
        selected_document_libraries_ids=["lib-1"],
        selected_document_uids=["doc-1"],
        search_rag_scope="corpus_only",
    )

    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed({"question": "hello"})

    assert injected["document_library_tags_ids"] == ["lib-1"]
    assert injected["document_uids"] == ["doc-1"]
    assert injected["session_id"] == "session-1"
    assert injected["team_id"] == "team-1"
    assert injected["owner_filter"] == "team"
    assert injected["include_session_scope"] is False
    assert injected["include_corpus_scope"] is True


def test_context_aware_tool_respects_agent_scoped_document_uids() -> None:
    """An explicit per-call document scope is honoured, never overwritten — and it
    suppresses the (widening) picker library filter so the search stays document-
    scoped. This is what lets a deterministic agent compare one document at a time."""
    runtime_context = RuntimeContext(
        selected_document_libraries_ids=["lib-1"],
        selected_document_uids=["doc-1", "doc-2"],
    )
    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed(
        {"question": "hello", "document_uids": ["doc-1"]}
    )

    # explicit scope respected, not replaced by the picker's [doc-1, doc-2]
    assert injected["document_uids"] == ["doc-1"]
    # the picker library filter is NOT injected on top of a document scope
    assert "document_library_tags_ids" not in injected


def test_context_aware_tool_respects_agent_scoped_library() -> None:
    """An explicit per-call library scope is honoured, not replaced by the picker."""
    runtime_context = RuntimeContext(
        selected_document_libraries_ids=["lib-picker"],
        selected_document_uids=["doc-1"],
    )
    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: runtime_context,
        agent_settings_provider=_FakeAgentSettings,
    )

    injected = wrapper._inject_context_if_needed(
        {"question": "hello", "document_library_tags_ids": ["lib-agent"]}
    )

    assert injected["document_library_tags_ids"] == ["lib-agent"]


class _RecordingKPIStore(BaseKPIStore):
    """Minimal BaseKPIStore that just remembers every emitted event."""

    def __init__(self) -> None:
        self.events: List[KPIEvent] = []

    def ensure_ready(self) -> None:
        return

    def index_event(self, event: KPIEvent) -> None:
        self.events.append(event)

    def bulk_index(self, events: List[KPIEvent]) -> None:
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        return KPIQueryResult(rows=[])


class _FailingTool(BaseTool):
    name: str = "fake.failing"
    description: str = "Tool that always raises, to exercise the KPI failure path."
    args_schema: ArgsSchema | None = _SearchArgs

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("boom")

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("boom")


def _install_recording_kpi_writer() -> _RecordingKPIStore:
    store = _RecordingKPIStore()
    set_runtime_context(
        GlobalRuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.test",
                kpi_writer=KPIWriter(store=store),
            )
        )
    )
    return store


def _latency_event(store: _RecordingKPIStore) -> KPIEvent:
    matches = [
        e for e in store.events if e.metric and e.metric.name == "agent.tool_latency_ms"
    ]
    assert len(matches) == 1
    return matches[0]


def test_context_aware_tool_run_success_leaves_default_ok_status() -> None:
    """A successful call doesn't need to set status explicitly — the timer's own
    __exit__ already defaults to "ok" when nothing overrides it. Asserting this
    (rather than an explicit "success" dim) locks in the codebase's established
    status vocabulary (ok|error|timeout|filtered|cancelled, see
    opensearch_kpi_store.py's index mapping)."""
    store = _install_recording_kpi_writer()
    wrapper = ContextAwareTool(
        base_tool=_FakeSearchTool(),
        context_provider=lambda: RuntimeContext(session_id="s1"),
        agent_settings_provider=_FakeAgentSettings,
    )

    result = wrapper._run(question="hello")

    assert result == "ok"
    assert _latency_event(store).dims["status"] == "ok"


def test_context_aware_tool_run_failure_sets_error_status() -> None:
    """Without the explicit override, the timer's __exit__ can't tell a caught
    exception happened (it never propagates out of the `with` block) and would
    default agent.tool_latency_ms to status="ok" even for a failed call."""
    store = _install_recording_kpi_writer()
    wrapper = ContextAwareTool(
        base_tool=_FailingTool(),
        context_provider=lambda: RuntimeContext(session_id="s1"),
        agent_settings_provider=_FakeAgentSettings,
    )

    wrapper._run(question="hello")

    assert _latency_event(store).dims["status"] == "error"


@pytest.mark.asyncio
async def test_context_aware_tool_arun_failure_sets_error_status() -> None:
    store = _install_recording_kpi_writer()
    wrapper = ContextAwareTool(
        base_tool=_FailingTool(),
        context_provider=lambda: RuntimeContext(session_id="s1"),
        agent_settings_provider=_FakeAgentSettings,
    )

    await wrapper._arun(question="hello")

    assert _latency_event(store).dims["status"] == "error"
