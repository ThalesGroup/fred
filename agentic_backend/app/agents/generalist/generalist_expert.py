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

# Fred architecture notes for implementers:
# - Graphs are built PER INSTANCE (self._graph) in async_init().
#   Why: LangGraph nodes call bound methods (they require `self`) and often depend on
#   per-instance state (model bindings, user tuning, runtime context). Building at class
#   import time would capture unbound functions and the wrong lifecycle.
# - Tuning is declared at CLASS LEVEL (Georges.tuning) because it is a static
#   “capability contract” for the UI. The user’s overrides live in AgentSettings.tuning
#   and are merged into the instance by AgentFlow.__init__/apply_settings.
# - No hidden prompt composition: each node explicitly decides which tuned text to use
#   and whether to include the (optional) chat context. This keeps behavior auditable.

import logging

from fred_core import get_model
from langgraph.graph import END, START, MessagesState, StateGraph

from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sets Georges’ base persona and boundaries. "
                "Adjust to shift tone/voice or emphasize constraints."
            ),
            required=True,
            default=(
                "You are a friendly generalist expert, skilled at providing guidance on a wide range "
                "of topics without deep specialization.\n"
                "Your role is to respond with clarity, providing accurate and reliable information.\n"
                "When appropriate, highlight elements that could be particularly relevant.\n"
                "In case of graphical representation, render mermaid diagrams code."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


@expose_runtime_source("agent.Georges")
class Georges(AgentFlow):
    tuning = TUNING

    async def async_init(self):
        """
        Instance lifecycle hook.
        - Bind your model here (per-instance): lets you apply runtime/provider settings safely.
        - Build the LangGraph here and store it on `self._graph`.
          This ensures nodes are bound to THIS instance (self) and can safely call instance methods.
        """

        self.model = get_model(self.agent_settings.model)
        # Build a tiny, linear graph:
        # START → expert (reasoner) → END
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("expert", self.reasoner)
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder

    async def reasoner(self, state: MessagesState):
        """
        Single-step reasoning node.
        Rationale:
        - We pull the tuned system prompt by key (no magic). If the user updated it in the UI,
          AgentFlow has already placed the latest value in this instance.
        - We render {tokens} through AgentFlow.render(...) to resolve simple placeholders.
        - We *optionally* append the chat context text if this node decides it’s relevant.
          (Convention: dev chooses; Fred does not inject chat context automatically.)
        - We then prepend it as a SystemMessage and call the model with the user messages.
        """
        # 1) choose the tuning field you want. In this case, the system prompt
        tpl = self.get_tuned_text("prompts.system") or ""
        # 2) render tokens. You should always do this to resolve {placeholders}
        #    (e.g. {current_time}, {agent_name}, {user_name}, etc.)
        sys = self.render(tpl)
        # 3) optionally add the chat context text (if any). It's up to the node to decide
        #    whether to use it or not.

        messages = self.with_system(sys, state["messages"])
        messages = self.with_chat_context_text(messages)
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}
