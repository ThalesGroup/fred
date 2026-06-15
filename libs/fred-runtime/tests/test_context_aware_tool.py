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

from typing import Any

from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import AgentTuning
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from fred_runtime.common.context_aware_tool import ContextAwareTool


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
    args_schema: type[BaseModel] | dict[str, Any] | None = _SearchArgs

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "ok"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return "ok"


class _FakeAgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None


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
        agent_settings_provider=lambda: _FakeAgentSettings(),
    )

    injected = wrapper._inject_context_if_needed({"question": "hello"})

    assert injected["document_library_tags_ids"] == ["lib-1"]
    assert injected["document_uids"] == ["doc-1"]
    assert injected["session_id"] == "session-1"
    assert injected["team_id"] == "team-1"
    assert injected["owner_filter"] == "team"
    assert injected["include_session_scope"] is False
    assert injected["include_corpus_scope"] is True
