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

"""LangChain adapter for the shared tool execution boundary (ReAct and Deep)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast

from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.prompt_utils import escape_reserved_prompt_tags
from fred_sdk.contracts.runtime import TracerPort
from fred_sdk.contracts.skills import SkillsPort
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.runtime_support.tool_execution import ToolExecution

from ..react_tool_binding import SELF_TRACED_TOOL_METADATA_KEY
from ..react_tracing import RUNTIME_TOOL_SPAN_NAME, tool_span


class ToolObservabilityMiddleware(AgentMiddleware):
    """Adapt the tool node without duplicating binder-owned trace spans."""

    def __init__(
        self,
        *,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
        tracer: TracerPort | None = None,
        skills: SkillsPort | None = None,
    ) -> None:
        super().__init__()
        self._execution = ToolExecution(kpi=kpi, binding=binding)
        self._binding = binding
        self._tracer = tracer
        self._skills = skills
        self._kpi = kpi

    @staticmethod
    def _tool_name(request: ToolCallRequest) -> str:
        tool_call = request.tool_call
        name = tool_call.get("name") if isinstance(tool_call, dict) else None
        if not name:
            name = getattr(request.tool, "name", None)
        return str(name) if name else "unknown"

    def _span_tracer(self, request: ToolCallRequest) -> TracerPort | None:
        """Skip binder-owned spans; middleware tools need their own span."""

        metadata = getattr(request.tool, "metadata", None) or {}
        if metadata.get(SELF_TRACED_TOOL_METADATA_KEY):
            return None
        return self._tracer

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tracer = self._span_tracer(request)
        tool_call = request.tool_call
        async with tool_span(
            tracer,
            name=RUNTIME_TOOL_SPAN_NAME,
            context=self._binding.portable_context,
            attributes={"tool_name": self._tool_name(request)},
            input_payload=tool_call.get("args")
            if isinstance(tool_call, dict)
            else None,
        ) as span:
            result = await self._execution.run(
                lambda: handler(request),
                tool_name=self._tool_name(request),
                source="mcp"
                if isinstance(request.tool, ContextAwareTool)
                else "capability",
                span=span,
            )
            skills = self._skills
            native_tool = self._tool_name(request)
            if skills is not None and native_tool in {
                "read_file",
                "ls",
                "glob",
                "grep",
            }:
                from fred_runtime.skills.native_reads import observe_skill_read

                def observe(message: object) -> object:
                    if not isinstance(
                        message, ToolMessage
                    ) or message.tool_call_id != tool_call.get("id"):
                        return message
                    if native_tool != "read_file":
                        return (
                            message.model_copy(
                                update={
                                    "content": escape_reserved_prompt_tags(
                                        message.content
                                    )
                                }
                            )
                            if message.status != "error"
                            and isinstance(message.content, str)
                            else message
                        )
                    return observe_skill_read(
                        message,
                        tool_call.get("args", {}),
                        skills=skills,
                        binding=self._binding,
                        kpi=self._kpi,
                    )

                if isinstance(result, ToolMessage):
                    result = cast(ToolMessage, observe(result))
                elif isinstance(result.update, dict) and isinstance(
                    result.update.get("messages"), (list, tuple)
                ):
                    result = replace(
                        result,
                        update={
                            **result.update,
                            "messages": [
                                observe(message)
                                for message in result.update["messages"]
                            ],
                        },
                    )
            if span is not None and tracer is not None and tracer.captures_content:
                output = getattr(result, "content", None)
                if isinstance(result, Command) and isinstance(result.update, dict):
                    messages = result.update.get("messages", [])
                    if isinstance(messages, (list, tuple)):
                        output = [
                            message.content
                            for message in messages
                            if isinstance(message, ToolMessage)
                            and message.tool_call_id == tool_call.get("id")
                        ]
                span.set_io(output=output)
            return result


__all__ = ["ToolObservabilityMiddleware"]
