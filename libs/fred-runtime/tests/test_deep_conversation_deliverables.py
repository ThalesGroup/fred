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
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.contracts.context import PublishedArtifact
from fred_sdk.contracts.runtime import (
    ConversationFileContent,
    ConversationFileEntry,
    WorkspaceFsPort,
)
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
        list=AsyncMock(
            return_value=(
                ConversationFileEntry(
                    document_id="doc",
                    content_id="read-version",
                    path="report.md",
                    name="report.md",
                    mime="text/markdown",
                    size=len(b"old report"),
                ),
            )
        ),
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
    listing = await invoke(next_turn, "list_conversation_files")
    assert isinstance(listing.content, str)
    listed = json.loads(listing.content)
    read = await invoke(
        next_turn,
        "read_conversation_file",
        document_id=listed["document_id"],
        workspace_path="/revision.md",
    )
    port.read.assert_awaited_once_with("doc", max_bytes=MAX_BYTES)
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
@pytest.mark.parametrize(
    "document_id,status",
    [("read-version", 404), ("missing-file", 404), ("not-a-uuid", 422)],
)
async def test_read_error_allows_relisting_and_correcting_only_the_file_identity(
    document_id,
    status,
):
    workspace = _scratchpad()
    port = catalogue()
    original = port.read.return_value
    port.read.side_effect = [
        httpx.HTTPStatusError(
            "private diagnostic",
            request=httpx.Request("GET", "https://cp.internal/files"),
            response=httpx.Response(status, json={"detail": "private diagnostic"}),
        ),
        original,
    ]
    middleware = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    result = await invoke(
        middleware,
        "read_conversation_file",
        document_id=document_id,
        workspace_path="/read.md",
    )
    assert result.artifact.is_error
    assert not result.artifact.ui_parts
    assert "list_conversation_files" in result.content
    assert "document_id" in result.content and "content_id" in result.content
    assert "private diagnostic" not in result.content
    assert "cp.internal" not in result.content
    assert not await workspace.exists("read.md")
    # The failed identifier is forwarded unchanged, with no revision lookup or fallback.
    port.read.assert_awaited_once_with(document_id, max_bytes=MAX_BYTES)

    listing = await invoke(middleware, "list_conversation_files")
    assert isinstance(listing.content, str)
    corrected = await invoke(
        middleware,
        "read_conversation_file",
        document_id=json.loads(listing.content)["document_id"],
        workspace_path="/read.md",
    )
    assert not corrected.artifact.is_error
    port.read.assert_awaited_with("doc", max_bytes=MAX_BYTES)
    assert await workspace.read_text("read.md") == "old report"
    port.write.assert_not_called()
    port.snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_read_transport_failure_returns_a_sanitized_retry_hint():
    workspace = _scratchpad()
    port = catalogue()
    port.read.side_effect = httpx.ReadError("private transport diagnostic")
    middleware = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    result = await invoke(
        middleware,
        "read_conversation_file",
        document_id="doc",
        workspace_path="/read.md",
    )
    assert result.artifact.is_error
    assert not result.artifact.ui_parts
    assert "Retry with the same document_id" in result.content
    assert "private transport diagnostic" not in result.content
    assert not await workspace.exists("read.md")
    port.write.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [401, 403, 500, AuthorityLostError(), DelegationUnavailableError()]
)
async def test_read_does_not_swallow_authority_loss_or_unexpected_failures(failure):
    workspace = _scratchpad()
    port = catalogue()
    error = (
        httpx.HTTPStatusError(
            "denied or failed",
            request=httpx.Request("GET", "https://cp.internal/files"),
            response=httpx.Response(failure),
        )
        if isinstance(failure, int)
        else failure
    )
    port.read.side_effect = error
    middleware = ConversationFilesMiddleware(
        workspace.port, cast(WorkspaceFsPort, port), "conversation"
    )
    with pytest.raises(type(error)) as raised:
        await invoke(
            middleware,
            "read_conversation_file",
            document_id="doc",
            workspace_path="/read.md",
        )
    assert raised.value is error
    assert not await workspace.exists("read.md")
    port.write.assert_not_called()


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
    occupied = await invoke(
        middleware,
        "read_conversation_file",
        document_id="doc",
        workspace_path="/report.md",
    )
    assert occupied.artifact.is_error
    assert "Choose another unused workspace_path" in occupied.content
    assert occupied.artifact.blocks[0].text == occupied.content
    assert await workspace.read_text("report.md") == "x" * (MAX_BYTES + 1)
    port.read.assert_not_awaited()
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
    read_tool = next(
        tool for tool in deliveries[0].tools if tool.name == "read_conversation_file"
    )
    description = read_tool.args["document_id"]["description"]
    assert "document_id from list_conversation_files" in description
    assert "Never use content_id" in description


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
