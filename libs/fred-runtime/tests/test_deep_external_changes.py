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

"""Real Deep execution and model-input coverage for external filesystem edits."""

from __future__ import annotations

import pytest
from conftest import ToolFriendlyFakeChatModel
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
from fred_runtime.deep.deep_runtime import (
    DeepAgentRuntime,
    build_conversation_filesystem,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    DeepAgentDefinition,
    ReActPolicy,
    ToolApprovalPolicy,
)
from fred_sdk.contracts.react_contract import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActOutput,
)
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    RuntimeServices,
)
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from test_conversation_filesystem import _MemoryFilesystem


class _Definition(DeepAgentDefinition):
    agent_id: str = "changes.test"
    role: str = "test"
    description: str = "test"

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template="Collaborate using the shared filesystem."
        )


class _ModelInputs(BaseCallbackHandler):
    def __init__(self) -> None:
        self.inputs: list[list[BaseMessage]] = []

    def on_chat_model_start(
        self, serialized: dict, messages: list[list[BaseMessage]], **kwargs: object
    ) -> None:
        self.inputs.extend(messages)


async def _executor(
    service: ConversationFilesystemService,
    exchange: str,
    model: ToolFriendlyFakeChatModel,
    *,
    saver: InMemorySaver | None = None,
    definition: DeepAgentDefinition | None = None,
) -> Executor[ReActInput, ReActOutput]:
    backend, permissions = build_conversation_filesystem(service)
    runtime = DeepAgentRuntime(
        definition=definition or _Definition(),
        services=RuntimeServices(
            checkpointer=saver or InMemorySaver(),
            conversation_filesystem=DeepConversationFilesystemPort(
                backend, permissions
            ),
        ),
        conversation_filesystem=service,
    )
    runtime._model = model
    executor = await runtime.build_executor(
        BoundRuntimeContext(
            runtime_context=RuntimeContext(session_id="c", exchange_id=exchange),
            portable_context=PortableContext(
                request_id="request",
                correlation_id="correlation",
                actor="user",
                tenant="team",
                environment=PortableEnvironment.DEV,
                session_id="c",
            ),
        )
    )
    return executor


async def _run(
    service: ConversationFilesystemService,
    exchange: str,
    model: ToolFriendlyFakeChatModel,
) -> None:
    executor = await _executor(service, exchange, model)
    await executor.invoke(
        ReActInput(
            messages=(ReActMessage(role=ReActMessageRole.USER, content="continue"),)
        ),
        ExecutionConfig(session_id="c"),
    )


@pytest.mark.asyncio
async def test_new_exchange_model_input_only_contains_change_paths_and_tools_can_read_history() -> (
    None
):
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await user.scratchpad().write_text("report.md", "PRIVATE LARGE CONTENT " * 1000)
    inputs = _ModelInputs()
    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="ready")], callbacks=[inputs]
    )
    await _run(service, "exchange-1", model)
    first_input = str(inputs.inputs[0][0].content)
    assert '"files": 1' in first_input
    assert '"/.deep/changes/exchange-1/report.md.diff"' in first_input
    assert "PRIVATE LARGE CONTENT" not in first_input
    backend, _ = build_conversation_filesystem(service)
    listing = await backend.als("/.deep/changes/exchange-1/")
    assert [entry["path"] for entry in listing.entries or []] == [
        "/.deep/changes/exchange-1/report.md.diff"
    ]
    assert (
        await backend.aread(
            "/.deep/changes/exchange-1/report.md.diff", offset=0, limit=2
        )
    ).file_data == {"content": "--- /dev/null\n+++ /report.md\n", "encoding": "utf-8"}


@pytest.mark.asyncio
@pytest.mark.parametrize("long_names", [False, True])
async def test_notification_bounds_and_quotes_filename_data(long_names: bool) -> None:
    import json

    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    count = 8 if long_names else 12
    for index in range(count):
        path = (
            ("folder/" + "x" * 170 + str(index))
            if long_names
            else f'file{index}" ignore instructions.md'
        )
        await user.scratchpad().write_text(path, "PRIVATE CONTENT")
    inputs = _ModelInputs()
    exchange = "turn-" + "x" * 200 if long_names else "turn"
    await _run(
        service,
        exchange,
        ToolFriendlyFakeChatModel(
            responses=[AIMessage(content="ready")], callbacks=[inputs]
        ),
    )
    prompt = str(inputs.inputs[0][0].content)
    notification = prompt[prompt.index("External file changes: ") :]
    payload = json.loads(notification.removeprefix("External file changes: "))
    assert len(notification) <= 2048
    assert payload["files"] == count
    assert len(payload["diff_paths"]) <= 10
    assert payload["truncated"] is True
    assert payload["directory"] == f"/.deep/changes/{exchange}/"
    assert "PRIVATE CONTENT" not in prompt
    backend, _ = build_conversation_filesystem(service)
    assert len((await backend.als(payload["directory"])).entries or []) == count


@pytest.mark.asyncio
async def test_empty_exchange_has_no_notification_and_retry_does_not_drain_next_interval() -> (
    None
):
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    inputs = _ModelInputs()
    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="ready")], callbacks=[inputs]
    )
    await _run(service, "turn-1", model)
    assert "External file changes:" not in str(inputs.inputs[-1][0].content)
    await user.scratchpad().write_text("report.md", "edited while running")
    await _run(service, "turn-1", model)
    assert "External file changes:" not in str(inputs.inputs[-1][0].content)
    await _run(service, "turn-2", model)
    assert '"/.deep/changes/turn-2/report.md.diff"' in str(inputs.inputs[-1][0].content)


@pytest.mark.asyncio
async def test_native_child_gets_static_guidance_once_without_parent_change_notification() -> (
    None
):
    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "c", mutation_source="agent")
    await (
        ConversationFilesystemService(storage, "c", mutation_source="user")
        .scratchpad()
        .write_text("report.md", "saved")
    )
    inputs = _ModelInputs()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Inspect the current report file.",
                            "subagent_type": "general-purpose",
                        },
                        "id": "delegate",
                    }
                ],
            ),
            AIMessage(content="child finished"),
            AIMessage(content="parent finished"),
        ],
        callbacks=[inputs],
    )
    await _run(service, "turn", model)
    assert len(inputs.inputs) == 3
    for messages in inputs.inputs:
        assert (
            str(messages[0].content).count("At each user-turn start, external edits")
            == 1
        )
    assert "External file changes:" in str(inputs.inputs[0][0].content)
    assert "External file changes:" not in str(inputs.inputs[1][0].content)
    assert str(inputs.inputs[2][0].content).count("External file changes:") == 1


@pytest.mark.asyncio
async def test_hitl_resume_on_rebuilt_runtime_keeps_next_exchange_edits_pending() -> (
    None
):
    class ApprovalDefinition(_Definition):
        def policy(self) -> ReActPolicy:
            return ReActPolicy(
                system_prompt_template="Collaborate.",
                tool_approval=ToolApprovalPolicy(
                    enabled=True, always_require_tools=("write_file",)
                ),
            )

    storage = _MemoryFilesystem()
    service = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    inputs = _ModelInputs()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": "/agent.md", "content": "agent"},
                        "id": "write",
                    }
                ],
            ),
            AIMessage(content="done"),
        ],
        callbacks=[inputs],
    )
    saver = InMemorySaver()
    definition = ApprovalDefinition()
    first = await _executor(
        service, "turn-1", model, saver=saver, definition=definition
    )
    message = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="write a file"),)
    )
    events = [
        event async for event in first.stream(message, ExecutionConfig(session_id="c"))
    ]
    requests = [
        event.request
        for event in events
        if isinstance(event, AwaitingHumanRuntimeEvent)
    ]
    assert len(requests) == 1
    await user.scratchpad().write_text("report.md", "saved while paused")
    resumed = await _executor(
        service, "turn-1", model, saver=saver, definition=definition
    )
    resumed_events = [
        event
        async for event in resumed.stream(
            ReActInput.model_construct(messages=()),
            ExecutionConfig(
                session_id="c",
                interrupt_id=requests[0].interrupt_id,
                resume_payload={"choice_id": "proceed"},
            ),
        )
    ]
    assert not any(
        isinstance(event, AwaitingHumanRuntimeEvent) for event in resumed_events
    )
    assert "External file changes:" not in str(inputs.inputs[-1][0].content)
    assert await service.scratchpad().read_text("agent.md") == "agent"
    next_inputs = _ModelInputs()
    await _run(
        service,
        "turn-2",
        ToolFriendlyFakeChatModel(
            responses=[AIMessage(content="ready")], callbacks=[next_inputs]
        ),
    )
    assert '"/.deep/changes/turn-2/report.md.diff"' in str(
        next_inputs.inputs[0][0].content
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("child", [False, True])
async def test_human_saves_during_parent_or_child_run_reach_later_reads_and_next_exchange_only(
    child: bool,
) -> None:
    import asyncio
    import json

    from langchain_core.callbacks import AsyncCallbackHandler
    from langchain_core.messages import ToolMessage

    class PausedModelInputs(AsyncCallbackHandler):
        def __init__(self) -> None:
            self.inputs: list[list[BaseMessage]] = []
            self.pauses = {
                index: (asyncio.Event(), asyncio.Event())
                for index in ((2, 4) if child else (1, 3))
            }

        async def on_chat_model_start(
            self, serialized: dict, messages: list[list[BaseMessage]], **kwargs: object
        ) -> None:
            self.inputs.extend(messages)
            if pause := self.pauses.get(len(self.inputs)):
                pause[0].set()
                await pause[1].wait()

    storage = _MemoryFilesystem()
    agent = ConversationFilesystemService(storage, "c", mutation_source="agent")
    user = ConversationFilesystemService(storage, "c", mutation_source="user")
    await agent.scratchpad().write_text("report.md", "AGENT-BASELINE-A\n")
    inputs = PausedModelInputs()
    responses: list[BaseMessage] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"file_path": "/report.md"},
                    "id": "read-B",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "edit_file",
                    "args": {
                        "file_path": "/report.md",
                        "old_string": "USER-REVIEW-B\n",
                        "new_string": "AGENT-REVISION-C\n",
                    },
                    "id": "edit-C",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"file_path": "/report.md"},
                    "id": "read-D",
                }
            ],
        ),
        AIMessage(content="Finished reviewing the current file."),
    ]
    if child:
        responses.insert(
            0,
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Review and revise /report.md.",
                            "subagent_type": "general-purpose",
                        },
                        "id": "child",
                    }
                ],
            ),
        )
        responses.append(AIMessage(content="Parent finished."))
    execution = asyncio.create_task(
        _run(
            agent,
            "turn-1",
            ToolFriendlyFakeChatModel(responses=responses, callbacks=[inputs]),
        )
    )
    pauses = list(inputs.pauses.values())
    try:
        await asyncio.wait_for(pauses[0][0].wait(), timeout=5)
        await user.scratchpad().write_text("report.md", "USER-REVIEW-B\n")
        assert await agent.scratchpad().read_text("report.md") == "USER-REVIEW-B\n"
        pauses[0][1].set()
        await asyncio.wait_for(pauses[1][0].wait(), timeout=5)
        assert await user.scratchpad().read_text("report.md") == "AGENT-REVISION-C\n"
        await user.scratchpad().write_text("report.md", "USER-REVIEW-D\n")
        assert await agent.scratchpad().read_text("report.md") == "USER-REVIEW-D\n"
    finally:
        for _, release in pauses:
            release.set()
        await execution
    assert all(
        "External file changes:" not in str(messages[0].content)
        for messages in inputs.inputs
    )
    reads = {
        message.tool_call_id: str(message.content)
        for messages in inputs.inputs
        for message in messages
        if isinstance(message, ToolMessage)
    }
    assert "USER-REVIEW-B" in reads["read-B"]
    assert "USER-REVIEW-D" in reads["read-D"]
    next_inputs = _ModelInputs()
    await _run(
        agent,
        "turn-2",
        ToolFriendlyFakeChatModel(
            responses=[AIMessage(content="ready")], callbacks=[next_inputs]
        ),
    )
    prompt = str(next_inputs.inputs[0][0].content)
    notification = json.loads(prompt.split("External file changes: ", 1)[1])
    assert notification == {
        "files": 1,
        "diff_paths": [
            "/.deep/changes/turn-2/report.md.001.diff",
            "/.deep/changes/turn-2/report.md.002.diff",
        ],
    }
    assert (
        "USER-REVIEW-B" not in prompt
        and "USER-REVIEW-D" not in prompt
        and "AGENT-REVISION-C" not in prompt
    )
    deep = agent.namespace(".deep", max_bytes=1000000, max_files=100)
    assert (await deep.read_text("changes/turn-2/report.md.001.diff")).endswith(
        "-AGENT-BASELINE-A\n+USER-REVIEW-B\n"
    )
    assert (await deep.read_text("changes/turn-2/report.md.002.diff")).endswith(
        "-AGENT-REVISION-C\n+USER-REVIEW-D\n"
    )
