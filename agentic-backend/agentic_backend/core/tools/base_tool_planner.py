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

# agentic_backend/core/tooling/planner.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from langchain_core.messages import BaseMessage

from agentic_backend.core.tools.tool_plan_structures import ToolPlanV1


class BaseToolPlanner(ABC):
    """
    Decides whether to:
    - call a tool
    - ask for clarification
    - answer without tools

    IMPORTANT:
    - This class NEVER executes tools.
    - It only produces a ToolPlan.

    Which planner to use?
    - Conversational agents: prefer the LLM tool-calling loop
      (see core/graphs/tool_loop.py) where the model selects tools directly
      from the MCP toolkit. No deterministic parser required.
    - Deterministic/admin flows: use DeterministicPlanner for strict JSON
      envelopes when you want users to specify {"tool": "<name>", "args": {...}}.
    """

    @abstractmethod
    async def plan(
        self,
        messages: List[BaseMessage],
        available_tools: List[str],
    ) -> ToolPlanV1: ...
