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

"""Compiled Deep-agent proof for the capability-free scratchpad tools."""

from __future__ import annotations

from typing import Any

import pytest
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.deep_runtime import (
    _build_conversation_backend,
    _build_deepagent_runtime_middleware,
    _create_compiled_deep_agent,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

_SAFE_FILESYSTEM_TOOLS = {
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
}


class _ScriptedModel(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    bound_tool_names: list[set[str]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "deep-compiled-filesystem-tools-test"

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ScriptedModel:
        del kwargs
        self.bound_tool_names.append({tool.name for tool in tools})
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        response = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=response)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="request-deep-filesystem",
            correlation_id="correlation-deep-filesystem",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


async def _drive(agent: Any) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    async for mode, update in agent.astream(
        {"messages": [HumanMessage(content="write and read the shared note")]},
        config={"configurable": {"thread_id": "compiled-filesystem-tools"}},
        stream_mode=["messages", "updates"],
    ):
        if mode == "updates" and isinstance(update, dict):
            updates.append(update)
    return updates


@pytest.mark.asyncio
async def test_compiled_deep_agent_can_use_safe_scratchpad_tools_without_capability(
    tmp_path: Any,
) -> None:
    model = _ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "write_file",
                        {
                            "file_path": "/scratchpad/note.txt",
                            "content": "shared note",
                        },
                        "write-note",
                    )
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call(
                        "read_file",
                        {"file_path": "/scratchpad/note.txt"},
                        "read-note",
                    )
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    binding = _binding()

    def middleware(*, child: bool = False) -> list[Any]:
        return _build_deepagent_runtime_middleware(
            tracer=None,
            kpi=None,
            binding=binding,
            approval_policy=ToolApprovalPolicy(),
            available_tool_names=_SAFE_FILESYSTEM_TOOLS,
            child=child,
        )

    filesystem = ConversationFilesystemService(
        LocalFilesystem(str(tmp_path)), "conversation-a"
    )
    agent = _create_compiled_deep_agent(
        model=model,
        tools=[],
        system_prompt="Use the shared scratchpad.",
        checkpointer=InMemorySaver(),
        middleware=middleware(),
        subagent_middleware=middleware(child=True),
        backend=_build_conversation_backend(filesystem),
    )

    updates = await _drive(agent)

    tool_messages = {
        message.tool_call_id: message
        for update in updates
        for value in update.values()
        if isinstance(value, dict)
        for message in value.get("messages") or []
        if isinstance(message, ToolMessage)
    }
    assert tool_messages["write-note"].status == "success"
    assert tool_messages["read-note"].status == "success"
    assert "shared note" in str(tool_messages["read-note"].content)
    assert model.bound_tool_names
    assert all(_SAFE_FILESYSTEM_TOOLS <= names for names in model.bound_tool_names)
    assert all("execute" not in names for names in model.bound_tool_names)
