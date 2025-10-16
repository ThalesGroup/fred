# app/agents/leader/simple_router.py

import logging
from typing import Literal, Sequence, TypedDict

from fred_core import get_model, get_structured_chain
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

# Import Pydantic for structured output
from pydantic import (  # Added ValidationError for robustness
    BaseModel,
    Field,
)

from app.core.agents.agent_flow import AgentFlow
from app.core.runtime_source import expose_runtime_source


# ----------------------------------------------------------------------
# 1. Pydantic-Compliant Structures
# ----------------------------------------------------------------------
class PlannedStep(BaseModel):
    """A single step in the execution plan, assigned to an expert."""

    expert: str = Field(
        description="The name of the single expert agent that will execute this task."
    )
    task: str = Field(
        description="A clear, concise instruction for the assigned expert to execute."
    )

    def __str__(self):
        return f"({self.expert}): {self.task}"


class StepPlan(BaseModel):
    """The complete execution plan."""

    steps: Sequence[PlannedStep] = Field(
        description="A sequence of steps required to achieve the objective."
    )

    def __str__(self):
        return "\n".join(
            f"Step {i + 1} ({s.expert}): {s.task}" for i, s in enumerate(self.steps)
        )


# The State object remains a TypedDict
class SimpleState(TypedDict):
    messages: Sequence[BaseMessage]
    objective: BaseMessage | None
    plan: StepPlan | None
    step_index: int
    progress: list[tuple[PlannedStep, Sequence[BaseMessage]]]


# ----------------------------------------------------------------------
# End Pydantic Structures
# ----------------------------------------------------------------------


logger = logging.getLogger(__name__)


# UI 'thought' helper from your original code
def mk_thought(
    *, label: str, node: str, task: str, content: str, extras: dict | None = None
) -> AIMessage:
    md = {"thought": content, "extras": {"label": label, "node": node, "task": task}}
    if extras:
        md["extras"].update(extras)
    return AIMessage(content="", response_metadata=md)


@expose_runtime_source("agent.SimpleRouter")
class SimpleRouter(AgentFlow):
    """
    A modern, simplified leader focused on robust planning and routing in one pass.
    Flow: Plan Once (with expert assignment) → Execute Steps → Respond.
    """

    # --- lifecycle / bootstrap ------------------------------------------------
    async def async_init(self):
        self.model = get_model(self.agent_settings.model).bind(temperature=0, top_p=1)
        self.experts: dict[str, AgentFlow] = {}
        self.compiled_expert_graphs: dict[str, CompiledStateGraph] = {}

        # Ensure agent_settings.model is provided for typed APIs
        if self.agent_settings.model is None:
            raise ValueError(
                "agent_settings.model must be set to a valid ModelConfiguration"
            )

        # Pylance fix for get_structured_chain (Ensuring schema is a BaseModel subclass)
        self.plan_chain = get_structured_chain(StepPlan, self.agent_settings.model)

        self._graph = self._build_graph()

    # --- expert registry (simplified) -----------------------------------------
    def reset_experts(self) -> None:
        self.experts.clear()
        self.compiled_expert_graphs.clear()

    def add_expert(
        self, name: str, instance: AgentFlow, compiled_graph: CompiledStateGraph
    ) -> None:
        self.experts[name] = instance
        self.compiled_expert_graphs[name] = compiled_graph

    # --- graph definition -----------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(SimpleState)
        builder.add_node("planning", self.plan)
        builder.add_node("execute", self.execute)
        builder.add_node("respond", self.respond)

        builder.add_edge(START, "planning")
        builder.add_conditional_edges("execute", self.should_continue)
        builder.add_edge("planning", "execute")
        builder.add_edge("respond", END)

        return builder

    # --- routing conditions ---------------------------------------------------
    def should_continue(self, state: SimpleState) -> Literal["execute", "respond"]:
        """Checks if there are more steps to execute."""
        plan = state.get("plan")
        # Explicit check against None and for step_index safety
        if plan is not None and state.get("step_index", 0) < len(plan.steps):
            return "execute"
        return "respond"

    # --- nodes ----------------------------------------------------------------
    async def plan(self, state: SimpleState) -> dict:
        """
        Generates the *complete* plan with expert assignments in a single structured call.
        """
        # Get the objective from the latest HumanMessage
        new_objective: HumanMessage | None = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if new_objective is None:
            # Raise a clear error if the input state is invalid
            raise ValueError("No human message found for objective. Cannot plan.")

        objective = new_objective.content
        experts_list = "\n".join(
            [
                # Safely handle get_description potentially returning None
                f"- **{name}**: {agent.get_description() or 'No description provided.'}"
                for name, agent in self.experts.items()
            ]
        )
        expert_names = ", ".join(self.experts.keys())

        prompt = (
            "You are a master planner. Your task is to generate the SHORTEST, most effective "
            "plan to answer the user's objective. Your plan must be a sequence of steps, "
            "where EACH step is assigned to EXACTLY ONE expert from the list.\n"
            "**Constraints:**\n"
            "1. Output must strictly conform to the `StepPlan` schema.\n"
            "2. Only use expert names from the list: " + expert_names + "\n"
            "3. Prefer a single step if one expert can fully answer the objective.\n\n"
            f"**Objective:** {objective}\n"
            f"**Available Experts:**\n{experts_list}\n"
            "Produce the final, minimal plan."
        )

        messages = self.with_system(
            "You are a pragmatic, minimalist planner. Generate the final plan now.",
            [HumanMessage(content=prompt)],
        )

        # Explicitly type hint the result (Pylance fix for model_validate confusion)
        new_plan: StepPlan = await self.plan_chain.ainvoke({"messages": messages})

        thought = mk_thought(
            label="plan", node="planning", task="planning", content=str(new_plan)
        )

        return {
            "messages": [thought],
            "plan": new_plan,
            "objective": new_objective,
            "step_index": 0,
            "progress": [],
            "traces": [f"Initial plan set with {len(new_plan.steps)} steps."],
        }

    async def execute(self, state: SimpleState) -> dict:
        """
        Executes the current step of the pre-assigned plan.
        """
        plan = state.get("plan")  # Use .get() to prevent direct access warnings
        idx = state.get("step_index", 0)

        # Check for plan existence and index boundary
        if plan is None or idx >= len(plan.steps):
            return {"step_index": idx + 1}

        planned_step = plan.steps[idx]
        expert_name = planned_step.expert
        task = planned_step.task
        task_number = idx + 1

        picking = mk_thought(
            label="expert_select",
            node="execute",
            task="routing",
            content=f"Executing step {task_number}: {task} assigned to {expert_name}",
        )

        compiled = self.compiled_expert_graphs.get(expert_name)
        if not compiled:
            error_msg = f"Expert {expert_name} not found or graph not compiled."
            logger.error(error_msg)
            fail = mk_thought(
                label="expert_missing",
                node="execute",
                task="routing",
                content=error_msg,
            )
            return {
                "messages": [picking, fail],
                "step_index": idx + 1,
                "traces": [f"Step {task_number} failed: {error_msg}"],
            }

        # Fix for "content" is not a known attribute of "None"
        objective_msg = state.get("objective")
        objective_content = (
            objective_msg.content
            if objective_msg and objective_msg.content
            else "Unknown objective."
        )

        step_conclusions = [sr[-1] for _, sr in state.get("progress", [])]

        # The job for the expert: explicit task
        task_job = f"Your main task is: '{task}'. The overall objective is: '{objective_content}'."
        expert_messages = step_conclusions + [SystemMessage(content=task_job)]

        response = await compiled.ainvoke({"messages": expert_messages})

        # Process expert output for tracing
        additional_messages: list[BaseMessage] = [picking]
        expert_description = (
            self.experts.get(expert_name).get_description()
            if self.experts.get(expert_name)
            else ""
        )

        for message in response.get("messages", []):
            md = message.response_metadata if message.response_metadata else {}
            md["extras"] = {
                **(md.get("extras") or {}),
                "node": "execute",
                "task": str(task),
                "task_number": task_number,
                "agentic_flow": expert_name,
                "expert_description": expert_description,
            }
            message.response_metadata = md
            additional_messages.append(message)

        return {
            "messages": additional_messages,
            "traces": [f"Step {task_number} ({task}) executed by {expert_name}."],
            "progress": state.get("progress", [])
            + [(planned_step, response.get("messages", []))],
            "step_index": idx + 1,
        }

    async def respond(self, state: SimpleState) -> dict:
        """
        Compresses step outputs into a single, final, objective-focused answer.
        """
        if self.model is None:
            self.model = get_model(self.agent_settings.model)

        # Gather all final outputs from expert steps
        step_conclusions_str = ""
        for planned_step, step_responses in state.get("progress", []):
            if step_responses:
                # Safely access content
                conclusion = step_responses[-1].content or ""
                step_conclusions_str += f"[{planned_step.expert}]: {conclusion}\n"

        progress_msg = mk_thought(
            label="respond",
            node="respond",
            task="finalize",
            content="Summarizing all steps…",
        )

        # Fix for "content" is not a known attribute of "None"
        objective_content = (
            state["objective"].content
            if state.get("objective")
            and state["objective"]
            and state["objective"].content
            else "The user's request."
        )

        # Final answer prompt
        prompt = (
            "You are Fred, the team leader. You must ONLY use the data provided below "
            "to formulate a single, clear, and succinct final answer to the user's objective.\n"
            "**Do not invent, omit, or speculate.**\n\n"
            f"**Objective:** {objective_content}\n"
            f"**Team Conclusions:**\n{step_conclusions_str.strip()}\n"
            "Final Answer:"
        )

        messages = self.with_chat_context_text([HumanMessage(content=prompt)])

        response = await self.model.ainvoke(messages)

        return {
            "messages": [
                progress_msg,
                AIMessage(
                    content=response.content,
                    response_metadata={
                        "extras": {"node": "respond", "task": "deliver final answer"}
                    },
                ),
            ],
            "traces": ["Delivered final response."],
        }
