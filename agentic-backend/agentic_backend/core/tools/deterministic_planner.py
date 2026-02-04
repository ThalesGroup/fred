# Copyright Thales 2025
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
# agentic_backend/core/tooling/deterministic_planner.py
from __future__ import annotations

import json
from typing import List

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, ValidationError

from agentic_backend.core.tools.base_tool_planner import BaseToolPlanner
from agentic_backend.core.tools.tool_plan_structures import (
    AskClarificationPlanV1,
    CallToolPlanV1,
    ToolPlanV1,
)


class ExplicitToolCallV1(BaseModel):
    tool: str
    args: dict = {}


class DeterministicPlanner(BaseToolPlanner):
    """
    Generic baseline planner (non-LLM, strict JSON envelope).

    Intended use:
      - Admin/debug flows where you want an explicit tool + args from the user.
      - Deterministic operator/batch agents where free-form NL is discouraged.
      - NOT recommended for conversational agents: users must send a JSON object
        like: {"tool": "<tool_name>", "args": {...}}. If they don’t, you’ll get
        a clarifying question instead of automatic tool selection.

    For interactive/chatty agents, prefer the LLM tool-calling loop (see
    core/graphs/tool_loop.py) so the model can pick tools from the MCP toolkit.
    """

    async def plan(
        self, messages: List[BaseMessage], available_tools: List[str]
    ) -> ToolPlanV1:
        last_user = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        if not last_user or not isinstance(last_user.content, str):
            return AskClarificationPlanV1(
                question="Please specify which tool to use.",
                expected_fields=["tool", "args"],
            )

        text = last_user.content.strip()

        try:
            payload = json.loads(text)
            call = ExplicitToolCallV1.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return AskClarificationPlanV1(
                question=(
                    "I couldn't parse a tool request. Please send a JSON object like:\n"
                    '{ "tool": "<tool_name>", "args": { ... } }\n\n'
                    f"Available tools: {', '.join(available_tools) if available_tools else '(none)'}"
                ),
                expected_fields=["tool", "args"],
            )

        if call.tool not in available_tools:
            return AskClarificationPlanV1(
                question=(
                    f"Unknown tool '{call.tool}'. "
                    f"Available tools: {', '.join(available_tools) if available_tools else '(none)'}"
                ),
                expected_fields=["tool"],
            )

        return CallToolPlanV1(
            tool_name=call.tool,
            args=call.args,
            rationale="User explicitly requested this tool.",
            confidence=1.0,
        )
