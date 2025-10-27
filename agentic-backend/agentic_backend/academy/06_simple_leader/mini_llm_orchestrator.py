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

import logging
from typing import Any, Dict, Sequence, TypedDict, cast

from fred_core import ModelConfiguration, get_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.leader.base_agent_selector import RoutingDecision
from agentic_backend.core.leader.leader_flow import LeaderFlow
from agentic_backend.core.leader.llm_agent_selector import LLMAgentSelector
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

DEFAULT_ROUTER_MODEL = "gpt-4o"
DEFAULT_ROUTER_TEMP = 0.3

DEFAULT_PROVIDER = "openai"

TUNING = AgentTuning(
    role="mini_llm_orchestrator",
    description=(
        "A minimal leader agent that routes tasks to experts using an LLM-based selector."
    ),
    tags=["orchestrator"],
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
        FieldSpec(
            key="router.temperature",
            type="number",
            title="Router Temperature",
            description="Temperature setting for the routing model.",
            default=DEFAULT_ROUTER_TEMP,
            ui=UIHints(group="Router Model"),
        ),
    ],
)


# ----------------------------------------------------------------------
## 1. Graph State
# ----------------------------------------------------------------------
class OrchestratorState(TypedDict):
    """Defines the minimal state passed between nodes in the LangGraph flow."""

    messages: Sequence[BaseMessage]
    objective: str | None  # The user's original query
    decision: RoutingDecision | None  # Output from the selector (expert name + task)
    expert_result: AIMessage | None  # The final result from the chosen expert


# ----------------------------------------------------------------------
## 2. Minimal Orchestrator Agent
# ----------------------------------------------------------------------
@expose_runtime_source("agent.MiniLLMOrchestrator")
class MiniLLMOrchestrator(LeaderFlow):
    """
    A minimal leader: uses LLMAgentSelector to Route, delegates to one Expert,
    and provides a final Answer.
    """

    # --- Lifecycle / Bootstrap ------------------------------------------------
    async def async_init(self):
        router_provider = self.get_tuned_text("router.provider")
        router_name = self.get_tuned_text("router.model_name")
        router_temp = self.get_tuned_number("router.temperature")
        router_cfg = ModelConfiguration(
            name=cast(str, router_name or DEFAULT_ROUTER_MODEL),
            provider=cast(str, router_provider or DEFAULT_PROVIDER),
            settings={"temperature": router_temp or DEFAULT_ROUTER_TEMP},
        )
        self.router_model = get_model(router_cfg)

        logger.info(
            f"[AGENTS] agent=mini_llm_orchestrator "
            f"model_provider={router_cfg.provider} "
            f"modelname={router_cfg.name} settings={router_cfg.settings}"
        )

        # Primary model for final response (if needed)
        self.model = get_model(router_cfg).bind(
            temperature=self.get_tuned_number("router.temperature"), top_p=1
        )

        # Expert registries
        self.experts: dict[str, AgentFlow] = {}
        self.compiled_expert_graphs: dict[str, CompiledStateGraph] = {}

        # Initialize the LLM-based AgentSelector (the core routing logic)
        self.selector = LLMAgentSelector(router_cfg)
        logger.info("LLMAgentSelector initialized successfully.")

        # Build the graph
        self._graph = self._build_graph()
        logger.info("LangGraph structure built: [route] -> [execute] -> [respond].")

    # --- Expert Registry (Standard LeaderFlow functionality) -------------------
    def reset_crew(self) -> None:
        logger.info("Resetting crew: clearing expert registries.")
        self.experts.clear()
        self.compiled_expert_graphs.clear()

    def add_expert(
        self, name: str, instance: AgentFlow, compiled_graph: CompiledStateGraph
    ) -> None:
        self.experts[name] = instance
        self.compiled_expert_graphs[name] = compiled_graph
        logger.info(f"Expert added to crew: {name}.")

    # --- Graph Definition (Route -> Execute -> Respond) -----------------------
    def _build_graph(self) -> StateGraph:
        # ... (Graph construction logic remains the same) ...
        builder = StateGraph(OrchestratorState)
        builder.add_node("route", self.route)
        builder.add_node("execute", self.execute)
        builder.add_node("respond", self.respond)

        builder.add_edge(START, "route")
        builder.add_edge("route", "execute")
        builder.add_edge("execute", "respond")
        builder.add_edge("respond", END)

        return builder

    # ----------------------------------------------------------------------
    ## 3. Graph Nodes
    # ----------------------------------------------------------------------

    async def route(self, state: OrchestratorState) -> Dict[str, Any]:
        """Node 1: Use the LLMAgentSelector to choose the expert and rephrase the task."""
        logger.info("NODE: route - Starting routing step.")

        # Get the latest HumanMessage (the objective)
        objective_msg = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if objective_msg is None:
            logger.error(
                "NODE: route - Critical error: No HumanMessage found in state."
            )
            raise ValueError("No human message found for objective. Cannot route.")

        # objective content might be str or list[Any], passed directly to selector for normalization
        objective = objective_msg.content
        logger.info(
            f"NODE: route - Extracted objective content (type {type(objective).__name__})."
        )

        # Call the LLM Selector's single method to get the combined decision
        decision: RoutingDecision = await self.selector.choose_and_rephrase(
            objective=objective, experts=self.experts
        )
        logger.info(f"NODE: route - Selector returned expert: {decision.expert_name}")

        # Log the decision for tracing/UI using an AIMessage thought
        thought = AIMessage(
            content="",
            response_metadata={
                "thought": f"Selected **{decision.expert_name}** (Rationale: {decision.rationale}). Task: '{decision.task}'",
                "extras": {"node": "route", "task": "route_and_rephrase"},
            },
        )
        logger.info(
            f"NODE: route - Task generated for expert: '{decision.task[:50]}...'"
        )

        # Ensure objective is stored as a string for later nodes
        objective_str = str(objective)

        return {
            "objective": objective_str,
            "decision": decision,
            "messages": [thought],  # Append thought to history
        }

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        """Node 2: Delegate the rephrased task to the selected expert."""
        logger.info("NODE: execute - Starting expert delegation.")

        decision = state.get("decision")
        if decision is None:
            logger.error("NODE: execute - Critical error: Routing decision is missing.")
            raise ValueError("Routing decision is missing in state.")

        expert_name = decision.expert_name
        expert_task = decision.task

        logger.info(
            f"NODE: execute - Delegating task to expert: {expert_name} with task: '{expert_task[:50]}...'"
        )

        expert_instance = self.experts.get(expert_name)
        compiled = self.compiled_expert_graphs.get(expert_name)

        if not expert_instance or not compiled:
            logger.error(
                f"NODE: execute - Expert '{expert_name}' or its compiled graph is missing."
            )
            raise ValueError(f"Expert '{expert_name}' not properly registered.")

        # The expert only receives the clean, rephrased task as a HumanMessage
        expert_messages = [HumanMessage(content=expert_task)]

        # Execute the expert's flow while preserving run configuration
        with self.delegated(expert_instance) as expert_config:
            logger.info("NODE: execute - Invoking expert's compiled graph.")
            response_state = await compiled.ainvoke(
                {"messages": expert_messages}, config=expert_config
            )

        # Get the expert's final response message
        expert_messages_list = response_state.get("messages", [])
        if not expert_messages_list:
            logger.warning(
                f"NODE: execute - Expert {expert_name} returned no messages."
            )
            expert_result = AIMessage(
                content="Expert returned an empty response.", response_metadata={}
            )
        else:
            expert_result: AIMessage = expert_messages_list[-1]
            logger.info(
                f"NODE: execute - Expert response received (Type: {type(expert_result).__name__})."
            )

        # Decorate the result for UI attribution
        md = expert_result.response_metadata or {}
        md["extras"] = {
            **(md.get("extras") or {}),
            "node": "execute",
            "task": expert_task,
            "agentic_flow": expert_name,
        }
        expert_result.response_metadata = md

        return {
            "expert_result": expert_result,
            "messages": [expert_result],  # Add the expert's result to history
        }

    async def respond(self, state: OrchestratorState) -> Dict[str, Any]:
        """Node 3: Package the expert's answer for the user."""
        logger.info("NODE: respond - Starting final answer formulation.")

        expert_result = state.get("expert_result")
        objective = state.get("objective")

        # This minimal step just relays the expert's content with context
        if expert_result is None:
            final_content = "I could not retrieve a definitive answer from the expert."
            logger.warning("NODE: respond - Expert result was missing in state.")
        else:
            final_content = f"**Query:** '{objective}'\n\n{expert_result.content}"
            logger.info(
                "NODE: respond - Expert result is available. Framing final content."
            )

        final_answer = AIMessage(
            content=final_content,
            response_metadata={
                "extras": {"node": "respond", "task": "deliver_final_answer"}
            },
        )
        logger.info("NODE: respond - Final AIMessage constructed. Flow complete.")

        return {"messages": [final_answer]}
