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
# Responder — a "real" LLM agent:
# - injects the tuned system prompt,
# - calls the configured model once,
# - returns the model's message as a state delta.

from __future__ import annotations

import logging

# If your project exposes a model factory, import it here:
from fred_core import get_model  # <- adjust to your codebase
from langchain_core.messages import AnyMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM = "You are a helpful, concise assistant."

TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="system.prompt",
            type="prompt",
            title="System Prompt",
            description="High-level persona/constraints for the agent.",
            required=True,
            default=DEFAULT_SYSTEM,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


@expose_runtime_source("agent.Responder")
class Responder(AgentFlow):
    tuning = TUNING

    async def async_init(self):
        # 1) Choose a model for this agent (keep it simple at first).
        # If you have per-agent config, pass an id/name to get_model(...).
        self.model = get_model(self.agent_settings.model)
        # 2) Build the graph (compilation is deferred to the framework).
        self._graph = self._build_graph()
        logger.info("Responder initialized. Graph built and model ready.")

    def _build_graph(self) -> StateGraph:
        g = StateGraph(MessagesState)
        g.add_node("answer", self.node)
        g.add_edge(START, "answer")
        g.add_edge("answer", END)
        return g

    async def node(self, state: MessagesState) -> MessagesState:
        sys_p = self.get_tuned_text("system.prompt") or ""

        # Inject the system prompt explicitly (you control when/what applies)
        msgs: list[AnyMessage] = self.with_system(sys_p, state["messages"])

        # Canonical, normalized model call — always returns AnyMessage
        ai: AnyMessage = await self.ask_model(self.model, msgs)

        # Delta helper produces the exact MessagesState update
        return self.delta(ai)
