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
# -----------------------------------------------------------------------------
# AssetResponder — An agent that fetches user-uploaded assets and includes their content in responses.
# This example demonstrates how to access and utilize user-specific files within an agent flow.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import List, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

# Import Fred base classes and types
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# --- Defaults ---
# This default should correspond to an asset key uploaded by the user
DEFAULT_CONFIG_FILE_KEY = "config.txt"
DEFAULT_REPLY_PROMPT = "You are a helpful assistant. You must answer the user's question, but first, include the content of the provided configuration file under the heading 'CONFIGURATION FILE CONTENT'."


# 1. Declare the Agent's state structure (minimal set)
class AssetResponderState(TypedDict):
    """The state tracking conversation messages."""

    messages: List[AnyMessage]


# 2. Declare tunables: allow the user to specify which asset key to use.
TUNING = AgentTuning(
    role="configuration tester",
    description="An agent that fetches a user-uploaded configuration file and includes its content in responses.",
    tags=["academy"],
    fields=[
        FieldSpec(
            key="config_file.key",
            type="text",
            title="Required Config File Key",
            description="The key of the configuration file (e.g., 'template.docx') installed by the admin user.",
            default=DEFAULT_CONFIG_FILE_KEY,
            ui=UIHints(group="Configuration File"),
        ),
    ],
)


@expose_runtime_source("agent.ConfigLoader")
class ConfigLoader(AgentFlow):
    tuning = TUNING
    _graph: StateGraph | None = None

    # 2. Runtime init: Initialize the asset service and graph
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self._graph = self._build_graph()
        logger.info(
            "[ACADEMY] ConfigurationTesterAgent initialized with configuration file access."
        )

    # Graph construction method
    def _build_graph(self) -> StateGraph:
        """The agent's state machine: START -> asset_node -> END."""
        g = StateGraph(AssetResponderState)
        g.add_node("asset_node", self.config_loader_node)
        g.add_edge(START, "asset_node")
        g.add_edge("asset_node", END)
        return g

    async def config_loader_node(
        self, state: AssetResponderState
    ) -> AssetResponderState:
        """
        Node 1: Fetches the configured asset content and returns it directly as the response.
        """
        # 1. Get the configured asset key from tuning
        config_file_key = self.get_tuned_text("config_file.key")
        # 2. Fetch the configuration content from the agent config storage (admin-managed)
        config_file_content = await self.fetch_agent_config_text(
            config_file_key or DEFAULT_CONFIG_FILE_KEY
        )

        # 4. Create the final AI message
        ai_response = AIMessage(content=config_file_content)

        # 5. Return the final delta.
        return self.delta(ai_response)
