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
from __future__ import annotations

import logging
from typing import Any, Dict, Type

from langgraph.graph import MessagesState, StateGraph
from langgraph.types import interrupt

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerRef
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.tools.tool_loop import build_tool_loop

logger = logging.getLogger(__name__)


class Custodian(AgentFlow):
    """
    Production-ready demo for MCP + HITL:
    - Uses LLM tool-calling to pick MCP tools.
    - Filesystem tools run directly.
    - Corpus tools require HITL confirmation before execution.
    """

    tuning = AgentTuning(
        role="Data & Corpus Custodian",
        description="Ensures safe and controlled management of documents and knowledge corpora.",
        tags=["corpus", "filesystem"],
        fields=[],
        mcp_servers=[
            MCPServerRef(id="mcp-knowledge-flow-fs"),
            MCPServerRef(id="mcp-knowledge-flow-corpus"),
        ],
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)

    def get_state_schema(self) -> Type:
        return MessagesState

    async def async_init(self, runtime_context: RuntimeContext) -> None:
        await super().async_init(runtime_context)
        # 2) Model + MCP
        self.model = get_default_chat_model()
        # Start MCP toolkit (filesystem + corpus servers from tunings)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())

        # 3) Graph
        self._graph = self._build_graph()

    # ---------------- Graph ----------------
    def _build_graph(self) -> StateGraph:
        if not self.mcp:
            raise RuntimeError("MCP runtime not initialized")

        tools = self.mcp.get_tools()

        def system_builder(state: MessagesState) -> str:
            return (
                "You are a corpus manager. Use MCP tools to act on files or corpora. "
                "Explain what you will do. If no tool is needed, answer directly."
            )

        def requires_hitl(tool_name: str) -> bool:
            return tool_name in {
                "build_corpus_toc",
                "revectorize_corpus",
                "purge_vectors",
            }

        async def hitl_callback(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
            decision = interrupt(
                {
                    "stage": "corpus",
                    "title": "Confirm corpus operation",
                    "question": (
                        f"I can execute `{tool_name}` on the corpus. Choose what to do and optionally add notes "
                        "before I touch the corpus."
                    ),
                    "choices": [
                        {
                            "id": "proceed",
                            "label": "Proceed with corpus action",
                            "description": "Run the requested corpus operation now.",
                            "default": True,
                        },
                        {
                            "id": "adjust",
                            "label": "Proceed with adjustments",
                            "description": "I'll include the notes you provide.",
                        },
                        {
                            "id": "cancel",
                            "label": "Cancel",
                            "description": "Do nothing for now.",
                        },
                    ],
                    "free_text": True,
                    "metadata": {"action": tool_name, "args": args},
                }
            )

            choice = decision.get("choice_id") or decision.get("answer")
            notes = decision.get("text") or decision.get("notes")
            if isinstance(choice, str):
                choice = choice.lower()

            if choice == "cancel":
                return {"cancel": True}

            if notes:
                return {"notes": str(notes).strip()}

            return {}

        return build_tool_loop(
            model=self.model,
            tools=tools,
            system_builder=system_builder,
            requires_hitl=requires_hitl,
            hitl_callback=hitl_callback,
        )

    async def aclose(self):
        if self.mcp:
            await self.mcp.aclose()
