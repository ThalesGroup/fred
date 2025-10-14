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

from fred_core import get_model
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph

from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

# Import Fred base classes and types
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# --- Defaults ---
# This default should correspond to an asset key uploaded by the user
DEFAULT_ASSET_KEY = "welcome.txt"
DEFAULT_REPLY_PROMPT = "You are a helpful assistant. You must answer the user's question, but first, include the content of the provided asset under the heading 'ASSET CONTENT'."


# 1. Declare the Agent's state structure (minimal set)
class AssetResponderState(TypedDict):
    """The state tracking conversation messages."""

    messages: List[AnyMessage]


# 2. Declare tunables: allow the user to specify which asset key to use.
TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="asset.key",
            type="text",
            title="Required Asset Key",
            description="The key of the user-uploaded file (e.g., 'template.docx') to use in the prompt.",
            default=DEFAULT_ASSET_KEY,
            ui=UIHints(group="User Assets"),
        ),
    ]
)


@expose_runtime_source("agent.AssetResponder")
class AssetResponder(AgentFlow):
    tuning = TUNING
    _graph: StateGraph | None = None

    # 2. Runtime init: Initialize the asset service and graph
    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self._graph = self._build_graph()
        logger.info("AssetResponderAgent initialized with asset access.")

    # Graph construction method
    def _build_graph(self) -> StateGraph:
        """The agent's state machine: START -> asset_node -> END."""
        g = StateGraph(AssetResponderState)
        g.add_node("asset_node", self.asset_responder_node)
        g.add_edge(START, "asset_node")
        g.add_edge("asset_node", END)
        return g

    async def asset_responder_node(
        self, state: AssetResponderState
    ) -> AssetResponderState:
        """
        Node 1: Fetches the configured asset content and returns it directly as the response.
        """
        # 1. Get the configured asset key from tuning
        asset_key = self.get_tuned_text("asset.key")
        # 2. Fetch the actual content of the asset (This is the core logic!)
        asset_content = await self.fetch_asset_text(asset_key or DEFAULT_ASSET_KEY)
        is_error = asset_content.startswith("[Asset Retrieval Error:")

        # 3. Fallback Logic
        if is_error:
            if asset_key == DEFAULT_ASSET_KEY:
                asset_content = await self.read_bundled_file(DEFAULT_ASSET_KEY)
                status_line = f"--- Asset Retrieval Failed ({asset_key}) ---"
                status_note = (
                    f"NOTE: Using bundled fallback asset '{DEFAULT_ASSET_KEY}'."
                )
            else:
                status_line = f"--- Asset Retrieval Failed ({asset_key}) ---"
                status_note = f"NOTE: The requested key '{asset_key}' failed, and no action was taken."
        else:
            # Case C: Asset fetch succeeded.
            status_line = f"--- Fetched Asset: {asset_key} ---"
            status_note = f"NOTE: The **remote** asset '{asset_key}' was used."

        # 3. Construct the final message (No LLM call needed for this simple echo)
        if status_note:
            final_response_content = f"{status_line}\n{status_note}\n\n{asset_content}"
        else:
            # Only the error case, where asset_content is the error string
            final_response_content = f"{status_line}\n\n{asset_content}"

        # 4. Create the final AI message
        ai_response = AIMessage(content=final_response_content)

        # 5. Return the final delta.
        return self.delta(ai_response)
