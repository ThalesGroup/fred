# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fred_agents.test_assistant.graph_agent import TestAssistantGraphAgent
from fred_agents.test_assistant.graph_state import TestState
from fred_agents.test_assistant.runtime_probe import ProbeInput, runtime_probe_step
from fred_sdk import GraphNodeContext
from fred_sdk.contracts.context import (
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
)
from pydantic import ValidationError


def _search_result(found: bool = True) -> dict[str, object]:
    return {
        "tool_ref": "document_access",
        "sources": [
            {
                "uid": "fixture",
                "title": "fixture",
                "content": "fixture marker",
                "score": 1.0,
            }
        ]
        if found
        else [],
    }


def test_probe_route_uses_existing_agent():
    workflow = TestAssistantGraphAgent().workflow
    assert workflow is not None
    assert workflow.routes["dispatch"]["runtime_probe"] == "runtime_probe"
    assert workflow.edges["runtime_probe"] == "finalize"


@pytest.mark.asyncio
async def test_expiry_repeats_bound_search_without_identity(monkeypatch):
    calls = []

    async def search(name, arguments):
        calls.append((name, arguments))
        return _search_result()

    wait = AsyncMock()
    monkeypatch.setattr("fred_agents.test_assistant.runtime_probe.asyncio.sleep", wait)
    context = SimpleNamespace(
        invoke_runtime_tool=search,
        emit_status=Mock(),
    )
    state = TestState(
        latest_user_text='runtime probe {"mode":"expiry","marker":"marker","hold_seconds":12}'
    )
    handler = getattr(runtime_probe_step, "__wrapped__", runtime_probe_step)
    result = await handler(state, cast(GraphNodeContext, context))
    text = result.state_update["final_text"]
    assert isinstance(text, str)
    data = json.loads(text.removeprefix("RUNTIME-PROBE "))
    assert data["before"] is True and data["after"] is True
    assert len(calls) == 2 and calls[0] == calls[1]
    wait.assert_awaited_once_with(12)
    assert calls[0] == (
        "search_documents",
        {"question": "runtime diagnostic fixture", "top_k": 8},
    )


def test_probe_hold_and_input_are_bounded():
    for hold in [-1, 901]:
        with pytest.raises(ValidationError):
            ProbeInput(mode="expiry", hold_seconds=hold)
    with pytest.raises(ValidationError):
        ProbeInput.model_validate({"mode": "retrieval", "identity": "untrusted"})


@pytest.mark.asyncio
async def test_missing_fixture_never_emits_baseline_success():
    context = SimpleNamespace(
        invoke_runtime_tool=AsyncMock(return_value=_search_result(False)),
        emit_status=Mock(),
    )
    result = await runtime_probe_step(
        TestState(
            latest_user_text='runtime probe {"mode":"retrieval","marker":"missing"}'
        ),
        cast(GraphNodeContext, context),
    )
    context.emit_status.assert_not_called()
    context.invoke_runtime_tool.assert_awaited_once_with(
        "search_documents", {"question": "runtime diagnostic fixture", "top_k": 8}
    )
    assert '"before": false' in str(result.state_update["final_text"])


@pytest.mark.asyncio
@pytest.mark.parametrize("found_after", [True, False])
async def test_expiry_records_second_search_start_and_reports_only_success(
    monkeypatch, found_after
):
    clock = [100.0]
    calls = []

    async def search(name, arguments):
        calls.append(clock[0])
        clock[0] += 20.0
        return _search_result(len(calls) == 1 or found_after)

    async def wait(seconds):
        clock[0] += seconds

    monkeypatch.setattr(
        "fred_agents.test_assistant.runtime_probe.time.time", lambda: clock[0]
    )
    monkeypatch.setattr("fred_agents.test_assistant.runtime_probe.asyncio.sleep", wait)
    context = SimpleNamespace(
        invoke_runtime_tool=search,
        emit_status=Mock(),
    )
    result = await runtime_probe_step(
        TestState(
            latest_user_text='runtime probe {"mode":"expiry","marker":"marker","hold_seconds":12}'
        ),
        cast(GraphNodeContext, context),
    )
    text = result.state_update["final_text"]
    assert isinstance(text, str)
    data = json.loads(text.removeprefix("RUNTIME-PROBE "))
    assert calls == [100.0, 132.0]
    assert data["before_at"] == 120.0
    assert data["after_at"] == calls[1]
    statuses = [call.args[0] for call in context.emit_status.call_args_list]
    assert ("runtime_probe_after" in statuses) is found_after


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("wrong_scope", [None, "query", "inventory"])
async def test_tabular_probe_uses_bound_scope_and_fixed_query(nested, wrong_scope):
    from fred_sdk.contracts.context import (
        ToolContentBlock,
        ToolContentKind,
        ToolInvocationResult,
    )
    from langchain_core.tools import StructuredTool

    alias = 'fixture"table'
    calls = []
    tools = []
    for name, fields in (
        ("list_tabular_documents", {}),
        ("describe_tabular_documents", {"document_uids": {"type": "array"}}),
        (
            "query_tabular_documents",
            {
                "sql": {"type": "string"},
                "dataset_uids": {"type": "array"},
                "max_rows": {"type": "integer"},
            },
        ),
    ):
        properties = (
            {"request": {"type": "object", "properties": fields}}
            if nested and fields
            else fields
        )
        tools.append(
            StructuredTool(
                name=f"mcp_fixture_{len(tools)}",
                description="Bound diagnostic tool",
                metadata={
                    "mcp_trusted_service": "knowledge_flow_tabular",
                    "mcp_tool_name": name,
                },
                args_schema={"type": "object", "properties": properties},
                func=lambda: None,
            )
        )

    async def invoke(wire_name, args):
        tool = next(tool for tool in tools if tool.name == wire_name)
        name = tool.metadata["mcp_tool_name"]
        calls.append((name, args))
        payload = {
            "list_tabular_documents": {
                "result": [{"document_uid": "selected"}]
                + ([{"document_uid": "other"}] if wrong_scope == "inventory" else [])
            },
            "describe_tabular_documents": {
                "result": [
                    {"document_uid": "selected", "tables": [{"query_alias": alias}]}
                ]
            },
            "query_tabular_documents": {
                "rows": [{"label": "expected marker"}],
                "dataset_uids": ["outside" if wrong_scope else "selected"],
                "query_aliases": [alias],
                "error": None,
            },
        }[name]
        return ToolInvocationResult(
            tool_ref=wire_name,
            blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data=payload),),
        ).model_dump(mode="json")

    context = SimpleNamespace(
        binding=SimpleNamespace(
            runtime_context=SimpleNamespace(selected_document_uids=["selected"])
        ),
        services=SimpleNamespace(
            tool_provider=SimpleNamespace(get_tools=lambda: tuple(tools))
        ),
        invoke_runtime_tool=invoke,
    )
    state = TestState(
        latest_user_text='runtime probe {"mode":"tabular","marker":"expected marker"}'
    )
    if wrong_scope:
        with pytest.raises(RuntimeError, match="scope mismatch"):
            await runtime_probe_step(state, cast(GraphNodeContext, context))
        if wrong_scope == "inventory":
            assert [name for name, _ in calls] == ["list_tabular_documents"]
        return
    result = await runtime_probe_step(state, cast(GraphNodeContext, context))
    assert '"tabular": true' in str(result.state_update["final_text"])
    args = calls[-1][1]
    if nested:
        args = args["request"]
    assert args == {
        "sql": 'SELECT label \nFROM "fixture""table" \nWHERE code = 1',
        "dataset_uids": ["selected"],
        "max_rows": 10,
    }
    assert [name for name, _ in calls] == [
        "list_tabular_documents",
        "describe_tabular_documents",
        "query_tabular_documents",
    ]


def test_tabular_probe_rejects_browser_authority_and_sql():
    with pytest.raises(ValidationError):
        ProbeInput.model_validate(
            {
                "mode": "tabular",
                "marker": "fixture",
                "sql": "SELECT anything",
                "document_uids": ["outside"],
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["retrieval", "expiry", "web"])
async def test_disabled_or_unapproved_tools_never_use_raw_ports(mode):
    raw_search, raw_web = AsyncMock(), AsyncMock()
    context = SimpleNamespace(
        services=SimpleNamespace(
            document_search=SimpleNamespace(search=raw_search),
            web_research=SimpleNamespace(execute=raw_web),
        ),
        invoke_runtime_tool=AsyncMock(side_effect=RuntimeError("tool unavailable")),
        emit_status=Mock(),
    )
    state = TestState(
        latest_user_text=f'runtime probe {{"mode":"{mode}","hold_seconds":1}}'
    )
    if mode == "web":
        result = await runtime_probe_step(state, cast(GraphNodeContext, context))
        assert '"unavailable":true' in str(result.state_update["final_text"])
    else:
        with pytest.raises(RuntimeError):
            await runtime_probe_step(state, cast(GraphNodeContext, context))
    raw_search.assert_not_awaited()
    raw_web.assert_not_awaited()


@pytest.mark.asyncio
async def test_refused_search_never_reports_retrieval_success():
    context = SimpleNamespace(
        invoke_runtime_tool=AsyncMock(
            return_value=ToolInvocationResult(
                tool_ref="search_documents",
                failure=ToolFailure(code=ToolFailureCode.scope_refused),
            ).model_dump(mode="json")
        ),
        emit_status=Mock(),
    )
    with pytest.raises(RuntimeError, match="approved document search failed"):
        await runtime_probe_step(
            TestState(latest_user_text='runtime probe {"mode":"retrieval"}'),
            cast(GraphNodeContext, context),
        )
    context.emit_status.assert_not_called()


@pytest.mark.asyncio
async def test_web_probe_uses_approved_tool_and_preserves_refusal_code():
    from fred_agents.test_assistant.runtime_probe import _ApprovedWebTools
    from fred_sdk.contracts.context import ToolContentBlock, ToolContentKind
    from fred_sdk.contracts.web_research import FetchRequest, WebResearchError

    result = ToolInvocationResult(
        tool_ref="web_research.fetch_url",
        failure=ToolFailure(code=ToolFailureCode.resource_unavailable),
        blocks=(
            ToolContentBlock(
                kind=ToolContentKind.TEXT, text='{"error_code":"unsafe_destination"}'
            ),
        ),
    )
    context = SimpleNamespace(
        invoke_runtime_tool=AsyncMock(return_value=result.model_dump(mode="json"))
    )
    port = _ApprovedWebTools(cast(GraphNodeContext, context))
    with pytest.raises(WebResearchError, match="unsafe_destination"):
        await port.execute(FetchRequest(url="http://127.0.0.1/"))
    name, arguments = context.invoke_runtime_tool.await_args.args
    assert name == "fetch_url"
    assert arguments["url"] == "http://127.0.0.1/"
    assert "operation" not in arguments
