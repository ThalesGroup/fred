# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deliveries use the CP receipt and the version read, across Deep turns."""

import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fred_runtime.deep.conversation_files import MAX_BYTES, ConversationFilesMiddleware
from fred_sdk.contracts.context import PublishedArtifact
from fred_sdk.contracts.runtime import ConversationFileContent, WorkspaceFsPort
from langchain_core.messages import ToolMessage
from test_deep_concat_files import _scratchpad


async def invoke(middleware, name, **args):
    tool = next(tool for tool in middleware.tools if tool.name == name)
    result = await tool.ainvoke(
        {"type": "tool_call", "id": "call", "name": name, "args": args}
    )
    assert isinstance(result, ToolMessage)
    return result


def catalogue():
    return SimpleNamespace(
        read=AsyncMock(
            return_value=ConversationFileContent(
                document_id="doc", content_id="read-version", content=b"old report"
            )
        ),
        list=AsyncMock(return_value=()),
        snapshot=AsyncMock(
            side_effect=AssertionError("Never refresh the read version")
        ),
        write=AsyncMock(
            return_value=PublishedArtifact(
                key="doc",
                document_uid="doc",
                content_id="published-version",
                file_name="report.md",
                size=10,
                href="/control-plane/v1/spaces/s/sessions/conversation/files/doc/content",
            )
        ),
    )


@pytest.mark.asyncio
async def test_next_turn_reads_edits_and_replaces_the_version_actually_read():
    workspace = _scratchpad()
    port = catalogue()
    first_turn = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    await workspace.write_text("draft.md", "new report")
    created = await invoke(
        first_turn,
        "publish_conversation_file",
        workspace_path="/draft.md",
        path="report.md",
    )
    assert isinstance(created.content, str)
    assert json.loads(created.content)["document_uid"] == "doc"
    assert port.write.call_args.kwargs["expected_content_id"] is None
    assert created.artifact.ui_parts[0].href.endswith("/doc/content")

    next_turn = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    read = await invoke(
        next_turn,
        "read_conversation_file",
        document_id="doc",
        workspace_path="/revision.md",
    )
    assert "content_id=read-version" in read.content
    assert await workspace.read_text("revision.md") == "old report"
    await workspace.port.edit_text("/revision.md", "old", "edited", origin="agent")
    # A concurrent update cannot be hidden by a fresh snapshot on submission.
    port.write.side_effect = httpx.HTTPStatusError(
        "content_changed",
        request=httpx.Request("POST", "http://cp/files"),
        response=httpx.Response(409),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await invoke(
            next_turn,
            "publish_conversation_file",
            workspace_path="/revision.md",
            path="report.md",
            expected_content_id="read-version",
        )
    assert port.write.call_args.args == (
        "outputs/conversation/report.md",
        b"edited report",
    )
    assert port.write.call_args.kwargs["expected_content_id"] == "read-version"
    port.snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_transport_uncertainty_returns_no_success_link_and_replay_key():
    workspace = _scratchpad()
    await workspace.write_text("report.csv", "a,b\n1,2\n")
    port = catalogue()
    port.write.side_effect = httpx.ReadError("lost response")
    middleware = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    result = await invoke(
        middleware,
        "publish_conversation_file",
        workspace_path="/report.csv",
        path="report.csv",
    )
    assert result.artifact.is_error
    assert not result.artifact.ui_parts
    key = port.write.call_args.kwargs["request_key"]
    assert key in result.content
    await invoke(
        middleware,
        "publish_conversation_file",
        workspace_path="/report.csv",
        path="report.csv",
        request_key=key,
    )
    assert port.write.call_args.kwargs["request_key"] == key
    assert port.write.call_args.kwargs["content_type"] == "text/csv"


@pytest.mark.asyncio
async def test_workspace_limits_and_internal_files_are_not_bypassed():
    workspace = _scratchpad()
    port = catalogue()
    middleware = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    await workspace.write_text("report.md", "x" * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        await invoke(
            middleware,
            "publish_conversation_file",
            workspace_path="/report.md",
            path="report.md",
        )
    with pytest.raises(ValueError, match="Markdown"):
        await invoke(
            middleware,
            "publish_conversation_file",
            workspace_path="/report.md",
            path="report.exe",
        )
    with pytest.raises(ValueError, match="unused"):
        await invoke(
            middleware,
            "read_conversation_file",
            document_id="doc",
            workspace_path="/report.md",
        )
    from fred_sdk.contracts.runtime import ConversationFilesystemPermissionError

    with pytest.raises(ConversationFilesystemPermissionError):
        await invoke(
            middleware,
            "read_conversation_file",
            document_id="doc",
            workspace_path="/.deep/report.md",
        )
    port.write.assert_not_called()


@pytest.mark.parametrize("child", [False, True])
def test_deep_registration_uses_the_bound_conversation_and_effective_workspace(child):
    from fred_runtime.deep.deep_runtime import _build_deepagent_runtime_middleware
    from fred_sdk.contracts.context import (
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
    )
    from fred_sdk.contracts.models import ToolApprovalPolicy
    from weaver_fixtures import local_binding

    binding = local_binding(
        "delivery",
        runtime_context=RuntimeContext(session_id="conversation"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="alice",
            tenant="space",
            environment=PortableEnvironment.DEV,
        ),
    )
    workspace = _scratchpad()
    middleware = _build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=binding,
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
        filesystem=workspace.port,
        catalogue=cast(WorkspaceFsPort, catalogue()),
        child=child,
    )
    deliveries = [
        item for item in middleware if isinstance(item, ConversationFilesMiddleware)
    ]
    assert len(deliveries) == 1
    assert {tool.name for tool in deliveries[0].tools} == {
        "list_conversation_files",
        "read_conversation_file",
        "publish_conversation_file",
    }
    # There is no caller-selected person, run, agent, space or session argument.
    for tool in deliveries[0].tools:
        assert not (
            {"person", "run", "agent", "space_id", "session_id"} & tool.args.keys()
        )


@pytest.mark.asyncio
async def test_executor_registers_delivery_tools_without_a_capability_filesystem(
    monkeypatch,
):
    import fred_runtime.deep.deep_runtime as deep
    from fred_sdk.contracts.context import RuntimeContext
    from fred_sdk.contracts.runtime import RuntimeServices
    from langchain_core.language_models.chat_models import BaseChatModel
    from test_deep_agent_middleware import (
        _binding,
        _fake_conversation_filesystem,
        _fake_definition,
        _FakeBinder,
        _FakeExecutor,
        _FakeResolver,
    )

    captured = {}
    monkeypatch.setattr(deep, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(deep, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(
        deep, "_create_compiled_deep_agent", lambda **kwargs: captured.update(kwargs)
    )
    port = catalogue()
    port.bind = lambda binding: None
    binding = _binding().model_copy(
        update={"runtime_context": RuntimeContext(session_id="conversation")}
    )
    runtime = deep.DeepAgentRuntime(
        definition=_fake_definition(),
        services=RuntimeServices(workspace_fs=cast(WorkspaceFsPort, port)),
        conversation_filesystem=_fake_conversation_filesystem(),
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())
    await runtime.build_executor(binding)
    for frame in ("middleware", "subagent_middleware"):
        assert any(
            isinstance(item, ConversationFilesMiddleware) for item in captured[frame]
        )
    assert "publish_conversation_file" in captured["system_prompt"]
