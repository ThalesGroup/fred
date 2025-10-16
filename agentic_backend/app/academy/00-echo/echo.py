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
# What this shows (Fred architecture):
# - An AgentFlow must define:
#   1) AgentTuning (UI-configurable fields),
#   2) async_init() that builds a LangGraph,
#   3) ≥1 node that returns a *state update* (not a full state rewrite).
# - This agent does NOT call an LLM. It’s only the minimal plumbing.
# - Hover comments explain *why* each method exists in Fred.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging

# LangChain / LangGraph primitives used by Fred
from langchain_core.messages import AIMessage  # "assistant" message object
from langgraph.graph import END, START, MessagesState, StateGraph

from app.core.agents.agent_flow import (
    AgentFlow,  # ⬅️ The base class all Fred agents extend
)
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

# Fred base types
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# STEP 1: AgentTuning — expose what the UI can change at runtime
# -----------------------------------------------------------------------------
# Why: Fred reads this schema to render controls and to provide "live" values
# (hot-swappable without restarting the agent).
DEFAULT_SYSTEM = "You are Echo, a minimal echo agent."

TUNING: AgentTuning = AgentTuning(
    fields=[
        FieldSpec(
            key="system.prompt",
            type="prompt",
            title="System Prompt",
            description="Defines the agent's role/persona. Editable live in the UI.",
            required=True,
            default=DEFAULT_SYSTEM,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


@expose_runtime_source("agent.Echo")
class Echo(AgentFlow):
    """
    Minimal AgentFlow:
    - declares `tuning`
    - builds a trivial graph in `async_init()`
    - has a single node that returns ONLY the new AIMessage
    """

    # Required: this lets Fred render the config panel and feed live values
    tuning = TUNING

    # -----------------------------------------------------------------------------
    # STEP 1: async_init — one-time setup (build the graph here, not compile)
    # -----------------------------------------------------------------------------
    async def async_init(self):
        # Why only build here: Fred compiles/attaches memory later to ensure
        # consistent setup across environments and hot-reloads.
        self._graph = self._build_graph()
        logger.info("Graph built.")

    def _build_graph(self) -> StateGraph:
        """
        MessagesState = running list of LangChain BaseMessages (user/assistant).
        Flow: START -> expert -> END
        """
        g = StateGraph(MessagesState)
        g.add_node("expert", self.node)  # single step
        g.add_edge(START, "expert")
        g.add_edge("expert", END)
        return g

    # -----------------------------------------------------------------------------
    # STEP 3: Node — must return a *state update* (delta), not a full state
    # -----------------------------------------------------------------------------
    async def node(self, state: MessagesState) -> MessagesState:
        """
        Called for each incoming user message.

        Why async: real agents will do I/O here (LLM/tool calls). Keeping the
        signature async avoids refactors later.
        """
        # Pull the live value from the UI at call time (hot-swappable)
        sys_p = self.get_tuned_text("system.prompt") or ""

        # Minimal demo content — no LLM call; just acknowledge config
        msg_content = f"Echo Agent Ready.\n• system.prompt: {sys_p}"

        # Return ONLY the new assistant message.
        # Why: prevents the StreamTranscoder from replaying history as observations.
        return {"messages": [AIMessage(content=msg_content)]}

    # -----------------------------------------------------------------------------
    # NEXT STEP (for devs): make it a real LLM agent
    # -----------------------------------------------------------------------------
    # 1) Inject the system prompt into the conversation:
    #       msgs = self.with_system(state["messages"], sys_p)
    # 2) Call the configured model:
    #       ai = await self.model.ainvoke(msgs)
    # 3) Return delta:
    #       return {"messages": [ai]}
