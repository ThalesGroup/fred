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

# -----------------------------------------------------------------------------
# DualModelResponder — A high-performance, multi-model agent using the Router/Generator pattern.
# It uses a fast, cheap model (Router) for classification and a powerful, more
# expensive model (Generator) for the final response.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import List, TypedDict, cast

from fred_core import get_model  # Your model factory
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from app.common.structures import ModelConfiguration
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


# DualModelResponderState: Defines the state passed between graph nodes.
class DualModelResponderState(TypedDict):
    """Extends MessagesState to track the LLM-determined routing classification."""

    messages: List[AnyMessage]
    classification: str  # Stores the Router's classification ('SIMPLE' or 'COMPLEX')


# --- Tuning and Defaults ---
# The Router Model is optimized for deterministic classification.
DEFAULT_ROUTER_SYSTEM = (
    "You are a routing expert. Classify the user message as 'SIMPLE' or 'COMPLEX'."
)
DEFAULT_ROUTER_MODEL = "gpt-4o-mini"
DEFAULT_ROUTER_TEMP = 0.0  # Low temperature for reliable output

# The Generator Model is optimized for high-quality, detailed content generation.
DEFAULT_GEN_SYSTEM = "You are a detailed, helpful assistant. Answer the user question."
DEFAULT_GEN_MODEL = "gpt-4o"
DEFAULT_GEN_TEMP = 0.3  # Higher temperature allows for more creativity

DEFAULT_PROVIDER = "openai"

# (TUNING block defines configurable fields for BOTH models)
TUNING = AgentTuning(
    fields=[
        # Router Model Configuration
        FieldSpec(
            key="router.provider",
            type="select",
            title="Router Provider",
            description="The model vendor for the fast classification model.",
            default=DEFAULT_PROVIDER,
            enum=["openai", "azure_openai", "ollama"],
            ui=UIHints(group="Router Model"),
        ),
        FieldSpec(
            key="router.model_name",
            type="text",
            title="Router Model ID",
            description="Fast model ID for routing (e.g., gpt-4o-mini).",
            default=DEFAULT_ROUTER_MODEL,
            ui=UIHints(group="Router Model"),
        ),
        # Generator Model Configuration
        FieldSpec(
            key="generator.model_name",
            type="text",
            title="Generator Model ID",
            description="High-quality model ID for final answer (e.g., gpt-4o).",
            default=DEFAULT_GEN_MODEL,
            ui=UIHints(group="Generator Model"),
        ),
        # ... (other tuning fields follow) ...
    ]
)


@expose_runtime_source("agent.DualModelResponder")
class DualModelResponder(AgentFlow):
    tuning = TUNING

    router_model: Runnable | None = None
    generator_model: Runnable | None = None

    async def async_init(self):
        # 1. Initialize the Router Model (Fast, Cheap)
        # Uses fully-tuned values for maximum control over behavior.
        router_provider = self.get_tuned_text("router.provider")
        router_name = self.get_tuned_text("router.model_name")
        router_temp = self.get_tuned_number("router.temperature")

        router_cfg = ModelConfiguration(
            name=cast(str, router_name or DEFAULT_ROUTER_MODEL),
            provider=cast(str, router_provider or DEFAULT_PROVIDER),
            settings={"temperature": router_temp or DEFAULT_ROUTER_TEMP},
        )
        self.router_model = get_model(router_cfg)

        # 2. Initialize the Generator Model (High-Quality, Capable)
        # Uses fully-tuned values for maximum control over generation quality.
        gen_provider = self.get_tuned_text("generator.provider")
        gen_name = self.get_tuned_text("generator.model_name")
        gen_temp = self.get_tuned_number("generator.temperature")

        gen_cfg = ModelConfiguration(
            name=cast(str, gen_name or DEFAULT_GEN_MODEL),
            provider=cast(str, gen_provider or DEFAULT_PROVIDER),
            settings={"temperature": gen_temp or DEFAULT_GEN_TEMP},
        )
        self.generator_model = get_model(gen_cfg)

        # 3. Build the graph (defines the multi-step flow)
        self._graph = self._build_graph()
        logger.info("DualModelResponder initialized with two fully-tuned models.")

    ## The LangGraph Flow Definition
    def _build_graph(self) -> StateGraph:
        """
        Defines the sequential flow: Router Model runs, updates state, then
        Generator Model runs, produces final answer.
        Flow: START -> router -> generator -> END
        """
        g = StateGraph(DualModelResponderState)
        g.add_node("router", self.router_node)
        g.add_node("generator", self.generator_node)

        # 1. Flow starts, goes to the classification model.
        g.add_edge(START, "router")

        # 2. After classification, flow proceeds directly to the generation model.
        # Note: If we had a third node (e.g., 'tool_executor'), this would be the
        # point to add conditional logic (e.g., if 'COMPLEX', go to 'tool_executor').
        g.add_edge("router", "generator")

        # 3. Final answer produced, graph ends.
        g.add_edge("generator", END)

        return g

    # --- LangGraph Nodes ---

    async def router_node(
        self, state: DualModelResponderState
    ) -> DualModelResponderState:
        """
        Node 1: Calls the small, deterministic Router Model (gpt-4o-mini).
        Its only job is to analyze the user message and save the 'classification'
        ('SIMPLE' or 'COMPLEX') into the shared state.
        """
        user_msg = cast(HumanMessage, state["messages"][-1])

        # Prompt the Router Model for a single classification word.
        router_prompt = (
            f"{DEFAULT_ROUTER_SYSTEM}. Classify the following request ONLY as "
            f"'SIMPLE' or 'COMPLEX'. Request: {user_msg.content}"
        )

        assert self.router_model is not None
        ai_response = await self.ask_model(
            self.router_model, [HumanMessage(content=router_prompt)]
        )

        classification = self._get_text_content(ai_response).strip().upper()

        logger.info(f"Router classified request as: {classification}")

        # Return the updated state dictionary.
        return {
            "messages": state["messages"],  # Preserve the conversation history
            "classification": classification,  # Add the classification result
        }

    async def generator_node(
        self, state: DualModelResponderState
    ) -> DualModelResponderState:
        """
        Node 2: Calls the powerful Generator Model (gpt-4o).
        It uses the 'classification' determined by the Router Model to potentially
        adjust its behavior (though here it's mainly for context/logging).
        It produces the final, user-facing answer.
        """
        classification = state.get("classification", "UNKNOWN")

        # System prompt integrates the Router's result for better quality/context.
        sys_p = f"You are a helpful assistant. The user's request was classified as {classification}. Provide a detailed and accurate answer."
        msgs = self.with_system(sys_p, state["messages"])

        assert self.generator_model is not None
        ai: AnyMessage = await self.ask_model(self.generator_model, msgs)

        # 'delta' adds the AI response to the message history.
        msg_update = self.delta(ai)

        # Return the final state with the answer and preserved classification.
        return {
            "messages": msg_update["messages"],
            "classification": classification,
        }
