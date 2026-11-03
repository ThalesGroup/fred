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
Context-injection tests for `ContextAwareTool`.

KPI timing (`agent.tool_latency_ms`) and the
`agent.tool.invocation.{started,completed}` audit events used to be tested
here directly; that behavior moved to the platform-wide
`ToolObservabilityMiddleware` (#2011) — see
`tests/test_tool_observability_middleware.py` for the equivalent coverage,
now exercised through `awrap_tool_call` for every tool call (MCP-catalog AND
capability-native), not just `ContextAwareTool`-wrapped ones.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import pytest
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_sdk.contracts.context import (
    RuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from langchain_core.messages import ToolMessage
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


class _ReadQueryArgs(BaseModel):
    sql: str


class _FailingReadQueryTool(BaseTool):
    name: str = "read_query"
    description: str = "Run a read-only query."
    args_schema: ArgsSchema | None = _ReadQueryArgs
    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"
    failure_message: str = (
        "Error calling read_query. Status code: 400. Response: "
        '{"detail":"Binder Error: Referenced column amount_typo not found"}'
    )

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError(self.failure_message)


class _FakeAgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


@pytest.mark.asyncio
@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.parametrize("structured", [False, True])
async def test_mcp_success_normalization_handles_sync_and_async_calls(
    async_call: bool, structured: bool
) -> None:
    payload: dict[str, object] = {"rows": [{"count": 12}]}

    class Provider(BaseTool):
        name: str = "read_query"
        description: str = "Read a count."
        response_format: Literal["content", "content_and_artifact"] = (
            "content_and_artifact"
        )

        def _run(self, **kwargs: Any) -> tuple[str, dict[str, object] | None]:
            return "12 cars", {"structured_content": payload} if structured else None

        async def _arun(self, **kwargs: Any) -> tuple[str, dict[str, object] | None]:
            return self._run(**kwargs)

    wrapper = ContextAwareTool(
        base_tool=Provider(),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )
    call = {"type": "tool_call", "id": "count", "name": wrapper.name, "args": {}}
    result = await wrapper.ainvoke(call) if async_call else wrapper.invoke(call)

    assert isinstance(result, ToolMessage)
    assert result.status == "success"
    assert result.content == "12 cars"
    if structured:
        assert isinstance(result.artifact, ToolInvocationResult)
        assert result.artifact.blocks == (
            ToolContentBlock(kind=ToolContentKind.JSON, data=payload),
        )
    else:
        assert result.artifact is None


@pytest.mark.asyncio
async def test_fastapi_mcp_read_query_400_returns_a_typed_sql_failure() -> None:
    """The model keeps a useful tool result while the runtime gets a trusted,
    HTTP-free SQL failure payload for the trace and observability layers."""
    wrapper = ContextAwareTool(
        base_tool=_FailingReadQueryTool(),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )

    content, artifact = await wrapper._arun(sql="SELECT amount_typo FROM d_sales")

    assert content == "Error: Binder Error: Referenced column amount_typo not found"
    assert "HTTP" not in content
    assert artifact is not None
    assert artifact.is_error is True
    assert len(artifact.blocks) == 1
    assert artifact.blocks[0].kind == ToolContentKind.TEXT
    assert artifact.blocks[0].text == (
        "Binder Error: Referenced column amount_typo not found"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_message",
    [
        (
            "Error calling read_query. Status code: 500. Response: "
            '{"detail":"internal provider secret"}'
        ),
        "Error calling read_query. Status code: 400. Response: not-json",
    ],
)
async def test_read_query_untrusted_failures_keep_only_the_generic_artifact(
    failure_message: str,
) -> None:
    wrapper = ContextAwareTool(
        base_tool=_FailingReadQueryTool(failure_message=failure_message),
        context_provider=lambda: None,
        agent_settings_provider=_FakeAgentSettings,
    )

    _content, artifact = await wrapper._arun(sql="SELECT secret FROM d_sales")

    assert artifact is not None
    assert artifact.is_error is True
    assert artifact.blocks == ()


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
    assert injected["include_session_scope"] is True
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


class _TabularTool(BaseTool):
    name: str = "list_tabular_documents"
    description: str = "List tabular documents."
    args_schema: ArgsSchema | None = {
        "type": "object",
        "properties": {
            "attachment_uids": {"type": "array", "items": {"type": "string"}},
            "include_session_scope": {"type": "boolean"},
            "include_corpus_scope": {"type": "boolean"},
            "corpus_document_uids": {"type": "array", "items": {"type": "string"}},
            "document_library_tags_ids": {"type": "array", "items": {"type": "string"}},
            "sql": {"type": "string"},
        },
    }
    calls: list[dict[str, Any]] = []

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError

    async def _arun(self, **kwargs: Any) -> str:
        kwargs.pop("config", None)
        self.calls.append(kwargs)
        return "ok"


@pytest.fixture
def tabular_wrapper(monkeypatch):
    from types import SimpleNamespace

    import fred_runtime.common.context_aware_tool as module
    import httpx

    context = RuntimeContext(
        session_id="session-1", team_id="team-1", access_token="test-token"
    )
    requests = []
    inventory = {
        "session-1": [{"document_uid": "attached-1"}],
        "session-2": [{"document_uid": "attached-2"}],
    }

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def _request_with_token_refresh(self, _method, path, **_kwargs):
            requests.append(path)
            session = path.split("/")[-2]
            if session not in inventory:
                raise httpx.HTTPStatusError(
                    "Forbidden",
                    request=httpx.Request("GET", "https://cp.invalid"),
                    response=httpx.Response(403),
                )
            return httpx.Response(200, json=inventory[session])

    monkeypatch.setattr(module, "KfBaseClient", Client)
    monkeypatch.setattr(
        module,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                control_plane_url="https://cp.invalid",
                control_plane_http_client=object(),
            )
        ),
    )
    agent = SimpleNamespace(
        runtime_context=context,
        agent_settings=_FakeAgentSettings(),
        document_access_config={"attachments": True, "team_documents": True},
    )
    agent.inventory = inventory
    tool = _TabularTool()
    wrapper = ContextAwareTool(
        tool,
        lambda: agent.runtime_context,
        lambda: agent.agent_settings,
        agent_context=agent,
    )
    return wrapper, tool, agent, requests


@pytest.mark.asyncio
async def test_tabular_no_argument_call_uses_authoritative_inventory(tabular_wrapper):
    wrapper, tool, _agent, requests = tabular_wrapper
    assert "attachment_uids" not in wrapper.args_schema["properties"]
    assert "attachment_uids" in tool.args_schema["properties"]
    assert (
        await wrapper._arun(
            attachment_uids=["forged"], session_id="forged", include_corpus_scope=False
        )
        == "ok"
    )
    assert tool.calls[-1]["attachment_uids"] == ["attached-1"]
    assert tool.calls[-1]["include_corpus_scope"] is True
    assert requests == ["/teams/team-1/sessions/session-1/attachments"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session", "corpus"), [(True, False), (False, True), (False, False)]
)
async def test_tabular_source_ceilings_cannot_be_widened(
    tabular_wrapper, session, corpus
):
    wrapper, tool, agent, requests = tabular_wrapper
    agent.document_access_config = {"attachments": session, "team_documents": corpus}
    await wrapper._arun(include_session_scope=True, include_corpus_scope=True)
    assert tool.calls[-1]["include_session_scope"] is session
    assert tool.calls[-1]["include_corpus_scope"] is corpus
    assert bool(requests) is session


@pytest.mark.asyncio
async def test_tabular_scope_refreshes_between_conversations_and_after_deletion(
    tabular_wrapper,
):
    wrapper, tool, agent, requests = tabular_wrapper
    await wrapper._arun()
    agent.runtime_context = agent.runtime_context.model_copy(
        update={"session_id": "session-2"}
    )
    await wrapper._arun()
    assert [call["attachment_uids"] for call in tool.calls] == [
        ["attached-1"],
        ["attached-2"],
    ]
    assert len(requests) == 2
    agent.inventory["session-2"] = []
    await wrapper._arun()
    assert tool.calls[-1]["attachment_uids"] == []
    assert tool.calls[-1]["include_session_scope"] is False


@pytest.mark.asyncio
async def test_tabular_membership_failure_does_not_call_tool(tabular_wrapper):
    wrapper, tool, agent, _requests = tabular_wrapper
    agent.runtime_context = agent.runtime_context.model_copy(
        update={"session_id": "refused-session"}
    )
    result = await wrapper._arun()
    assert "Error:" in result
    assert tool.calls == []


@pytest.mark.asyncio
async def test_tabular_general_only_has_no_document_inventory(tabular_wrapper):
    wrapper, tool, agent, requests = tabular_wrapper
    agent.runtime_context = agent.runtime_context.model_copy(
        update={"search_rag_scope": "general_only"}
    )
    await wrapper._arun()
    assert tool.calls[-1]["include_session_scope"] is False
    assert tool.calls[-1]["include_corpus_scope"] is False
    assert requests == []


@pytest.mark.asyncio
async def test_tabular_library_and_document_selection_are_kept_separate(
    tabular_wrapper,
):
    wrapper, tool, agent, _requests = tabular_wrapper
    agent.document_access_config.update(
        bind_libraries=True,
        library_tag_ids=["finance"],
        document_uids=["picked", "another"],
    )
    agent.runtime_context = agent.runtime_context.model_copy(
        update={
            "selected_document_libraries_ids": ["outside"],
            "selected_document_uids": ["picked"],
        }
    )
    await wrapper._arun()
    assert tool.calls[-1]["document_library_tags_ids"] == []
    assert tool.calls[-1]["corpus_document_uids"] == ["picked"]
    assert tool.calls[-1]["include_corpus_scope"] is True
    agent.runtime_context = agent.runtime_context.model_copy(
        update={"selected_document_uids": ["outside"]}
    )
    await wrapper._arun()
    assert tool.calls[-1]["include_corpus_scope"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_model", ["react", "deep"])
async def test_native_agents_share_tabular_discovery_scope(
    tabular_wrapper, execution_model, tmp_path
):
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, HumanMessage
    from test_deep_compiled_filesystem_tools import _ScriptedModel

    wrapper, _tool, agent, requests = tabular_wrapper
    tools = []
    names = ["list_tabular_documents", "describe_tabular_documents", "read_query"]
    for name in names:
        base = _TabularTool(name=name)
        tools.append(
            ContextAwareTool(
                base,
                lambda: agent.runtime_context,
                lambda: agent.agent_settings,
                agent_context=agent,
            )
        )
    model = _ScriptedModel(
        disable_streaming=True,
        custom_get_token_ids=lambda text: list(range(len(text) // 4)),
        script=[
            AIMessage(
                content="", tool_calls=[{"id": str(index), "name": name, "args": args}]
            )
            for index, (name, args) in enumerate(
                zip(
                    names,
                    [
                        {},
                        {"document_uids": ["attached-1"]},
                        {
                            "dataset_uids": ["attached-1"],
                            "sql": "SELECT COUNT(*) FROM attachment",
                        },
                    ],
                    strict=True,
                )
            )
        ]
        + [AIMessage(content="done")],
    )
    import asyncio

    if execution_model == "react":
        compiled = create_agent(model=model, tools=tools)
        result = await asyncio.wait_for(
            compiled.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content="Discover, describe and query my spreadsheets"
                        )
                    ]
                }
            ),
            timeout=10,
        )
        assert result["messages"][-1].content == "done"
    else:
        from fred_core.filesystem.local_filesystem import LocalFilesystem
        from fred_runtime.conversation_filesystem import ConversationFilesystemService
        from fred_runtime.deep.deep_runtime import (
            _create_compiled_deep_agent,
            build_conversation_filesystem,
        )
        from langgraph.checkpoint.memory import InMemorySaver

        filesystem = ConversationFilesystemService(
            LocalFilesystem(str(tmp_path)), "conversation-a"
        )
        backend, permissions = build_conversation_filesystem(filesystem)
        compiled = _create_compiled_deep_agent(
            model=model,
            tools=tools,
            system_prompt="Discover, describe and query",
            checkpointer=InMemorySaver(),
            middleware=[],
            subagent_middleware=[],
            backend=backend,
            permissions=permissions,
        )
        tool_node = getattr(compiled, "get_graph")().nodes["tools"].data
        for index, (name, args) in enumerate(
            zip(
                names,
                [
                    {},
                    {"document_uids": ["attached-1"]},
                    {
                        "dataset_uids": ["attached-1"],
                        "sql": "SELECT COUNT(*) FROM attachment",
                    },
                ],
                strict=True,
            )
        ):
            registered_tool = tool_node.tools_by_name[name]
            assert isinstance(registered_tool, ContextAwareTool)
            assert await registered_tool._arun(**args) == "ok"
    assert len(requests) == 3
    assert [tool.base_tool.calls[0]["attachment_uids"] for tool in tools] == [
        ["attached-1"]
    ] * 3
