# app/core/agents/leader_pure_llm_expert_picker.py

from __future__ import annotations

import json  # <-- ADDED (for objective serialization)
import logging  # <-- ADDED
from typing import Any, Dict, Sequence, cast

from fred_core import get_structured_chain
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_backend.common.structures import ModelConfiguration
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.leader.base_agent_selector import BaseAgentSelector, RoutingDecision

logger = logging.getLogger(__name__)  # <-- ADDED


# -------------------------------
# Helper for prompt UX (Assumed from previous context)
# -------------------------------
def experts_markdown(names: Sequence[str], experts: Dict[str, AgentFlow]) -> str:
    """Creates a markdown list of expert names and descriptions."""
    return "\n".join(
        f"- **{n}**: {experts[n].agent_settings.description or 'No description provided.'}"
        for n in names
        if n in experts
    )


class LLMAgentSelector(BaseAgentSelector):
    """
    Implements the BaseAgentSelector protocol using a single structured LLM call
    to choose the expert and generate the focused task.
    """

    def __init__(self, model_config: ModelConfiguration):
        self.model_config = model_config
        logger.info(
            f"LLMAgentSelector initialized with model: {model_config.name} (Provider: {model_config.provider})"
        )
        self.choose_chain = get_structured_chain(RoutingDecision, model_config)

    async def choose_and_rephrase(
        self,
        *,
        objective: str | list[Any],
        experts: Dict[str, AgentFlow],
    ) -> RoutingDecision:
        """
        Uses a single structured LLM call to select the expert, generate the task, and provide a rationale.
        """
        logger.info("Starting expert selection process (choose_and_rephrase).")

        expert_names = list(experts.keys())
        if not expert_names:
            logger.error("Expert list is empty. Cannot perform selection.")
            raise ValueError("No experts available for selection.")

        logger.info(f"Available experts: {', '.join(expert_names)}")

        # 1. Input Normalization: Convert complex 'objective' type to a clean string
        if isinstance(objective, str):
            objective_str: str = objective
            logger.info("Objective content is already a string.")
        else:
            try:
                objective_str = json.dumps(objective, ensure_ascii=False)
                logger.info(
                    f"Objective content serialized from {type(objective).__name__} to string for prompt."
                )
            except Exception as e:
                objective_str = str(objective)
                logger.warning(
                    f"Failed to JSON serialize objective. Using generic str() representation. Error: {e}"
                )

        available_experts_markdown = experts_markdown(expert_names, experts)

        system_prompt = (
            "You are a master router and task rephraser. Your output must strictly adhere "
            "to the RoutingDecision schema. Select the single best expert from the list "
            "to answer the objective and generate a highly focused, concise 'task' for them. "
            "The 'task' is the exact, clean instruction the expert will execute."
        )

        human_prompt = (
            f"**User Objective (Overall Goal):** {objective_str}\n"
            f"**Available Expert Options (Choose ONE expert_name):** {', '.join(expert_names)}\n\n"
            f"**Expert Details:**\n{available_experts_markdown}\n\n"
            "Based on the objective, make your selection."
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]

        logger.info("Invoking structured model for routing decision.")

        raw_result = await self.choose_chain.ainvoke({"messages": messages})
        decision: RoutingDecision = cast(RoutingDecision, raw_result)

        logger.info(
            f"Structured model returned raw decision. Expert: {decision.expert_name}"
        )

        # 2. Validation (in case the LLM hallucinates an expert name)
        if decision.expert_name not in expert_names:
            old_name = decision.expert_name
            decision.expert_name = expert_names[0]
            # Updated the warning/print statement to use the logger
            logger.warning(
                f"LLM chose invalid expert '{old_name}'. Falling back to first available expert: '{decision.expert_name}'. Validation required fallback."
            )
        else:
            logger.info(
                f"Validation successful. Chosen expert: '{decision.expert_name}' is valid."
            )

        logger.info(
            f"Final Routing Decision: Expert='{decision.expert_name}', Task='{decision.task[:50]}...'"
        )
        return decision
