# app/agents/leader/leader.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from difflib import get_close_matches
import logging
from typing import Literal

from langgraph.graph.state import StateGraph, CompiledStateGraph
from langgraph.constants import START, END
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.common.structures import AgentSettings
from app.core.model.model_factory import get_model
from app.core.agents.flow import AgentFlow
from app.agents.leader.structures.state import State
from app.agents.leader.structures.plan import Plan
from app.agents.leader.structures.decision import ExecuteDecision, PlanDecision

logger = logging.getLogger(__name__)


def mk_thought(*, label: str, node: str, task: str, content: str, extras: dict | None = None) -> AIMessage:
    """
    Emit an assistant-side 'thought' for the UI.
    UI renders response_metadata['thought'] under the Thoughts accordion.
    Additional routing/context info goes into response_metadata['extras'].
    """
    md = {"thought": content, "extras": {"label": label, "node": node, "task": task}}
    if extras:
        md["extras"].update(extras)
    return AIMessage(content="", response_metadata=md)


def _ensure_metadata_dict(msg: BaseMessage) -> dict:
    md = getattr(msg, "response_metadata", None) or {}
    if not isinstance(md, dict):
        md = {}
    msg.response_metadata = md
    return md

def _normalize_choice(raw: str, options: list[str]) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    # exact
    if raw in options:
        return raw
    # case-insensitive
    lower_map = {o.lower(): o for o in options}
    if raw.lower() in lower_map:
        return lower_map[raw.lower()]
    # fuzzy (handles minor typos)
    match = get_close_matches(raw, options, n=1, cutoff=0.6)
    return match[0] if match else None

class Leader(AgentFlow):
    """
    Fred is an agentic flow chatbot that uses a plan-and-supervisor approach
    with ReAct experts. It manages a dynamic list of experts that can be
    updated during the session.
    """

    # Class-level metadata
    name: str = "Fred"
    role: str = "Team Leader"
    nickname: str = "Fred"
    description: str = "Supervises multiple experts to provide answers and insights."
    icon: str = "fred_agent"
    tag: str = "leader"

    def __init__(self, agent_settings: AgentSettings):
        # Defer heavy setup to async_init to match your pattern
        self.agent_settings = agent_settings
        self.max_steps = agent_settings.max_steps

        # Will be set in async_init()
        self.model = None
        self._graph: StateGraph | None = None

        # Expert registry
        self.experts: dict[str, AgentFlow] = {}
        self.compiled_expert_graphs: dict[str, CompiledStateGraph] = {}

    async def async_init(self):
        """Async setup: model + graph, then call base __init__ like GeneralistExpert."""
        self.model = get_model(self.agent_settings.model)
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt="",                # add a base prompt later if you want
            categories=["orchestrator"],
            tag=self.tag,
        )

    # -------------------------
    # Expert management
    # -------------------------
    def reset_experts(self) -> None:
        logger.info("Resetting Fred experts. Previous experts: %s", list(self.experts.keys()))
        self.experts = {}
        self.compiled_expert_graphs = {}

    def add_expert(self, name: str, instance: AgentFlow, compiled_graph: CompiledStateGraph) -> None:
        """Register an expert and its compiled graph."""
        self.experts[name] = instance
        self.compiled_expert_graphs[name] = compiled_graph

    # -------------------------
    # Graph definition
    # -------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(State)
        builder.add_node("planning", self.plan)
        builder.add_node("supervise", self.supervise)
        builder.add_node("execute", self.execute)
        builder.add_node("validate", self.validate)
        builder.add_node("respond", self.respond)

        builder.add_edge(START, "planning")
        builder.add_edge("planning", "supervise")
        builder.add_conditional_edges("supervise", self.should_validate)
        builder.add_edge("execute", "supervise")
        builder.add_conditional_edges("validate", self.should_replan)
        builder.add_edge("respond", END)

        logger.info("Created Fred graph")
        return builder

    # -------------------------
    # Routing conditions
    # -------------------------
    async def should_validate(self, state: State) -> Literal["execute", "validate"]:
        progress = state.get("progress") or []
        max_steps = self.max_steps if self.max_steps is not None else 0
        if max_steps and len(progress) >= max_steps:
            logger.warning("Reached max_steps=%s, forcing final answer.", self.max_steps)
            return "validate"
        if len(progress) == len(state["plan"].steps):
            return "validate"
        return "execute"

    async def should_replan(self, state: State) -> Literal["respond", "planning"]:
        plan_decision = state.get("plan_decision")
        if plan_decision is not None and getattr(plan_decision, "action", None) == "planning":
            return "planning"
        return "respond"

    # -------------------------
    # Nodes
    # -------------------------
    async def respond(self, state: State):
        if self.model is None:
            self.model = get_model(self.agent_settings.model)

        step_conclusions_str = ""
        for _, step_responses in state.get("progress") or []:
            step_conclusions_str += f"{step_responses[-1].content}\n"

        # light progress thought
        progress_msg = mk_thought(
            label="respond",
            node="respond",
            task="finalize",
            content="Summarizing all step conclusions into a final answer…",
        )

        prompt = (
            "In your responses you will only use data retrieved from the different agents.\n"
            "Some of your agents are theorical which means that for a live data analysis you need to avoid querying them.\n"
            f"You executed this plan:\n{state['plan']}\n"
            f"For each step you came up with the following conclusions:\n{step_conclusions_str}\n"
            f"Given all these conclusions, what is your final answer to the question :{state['objective']}"
        )

        response = await self.model.ainvoke([HumanMessage(content=prompt)])
        response = AIMessage(  # ensure assistant role, downstream sets channel="final"
            content=response.content,
            response_metadata={"extras": {"node": "respond", "task": "deliver final answer"}},
        )

        return {"messages": [progress_msg, response], "traces": ["Responded to the user."]}

    async def plan(self, state: State):
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")

        # Find last human message as new objective
        new_objective = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        if new_objective is None:
            raise ValueError("No human message found for objective.")

        # Initialize objective/plan/progress on first run
        if "initial_objective" not in state:
            state["progress"] = []
            state["plan"] = Plan(steps=[])
            state["initial_objective"] = new_objective

        # Reset when the objective changes
        if state["initial_objective"] is None or state["initial_objective"].content != new_objective.content:
            logger.info("New initial objective detected. Resetting plan and progress.")
            state["progress"] = []
            state["plan"] = Plan(steps=[])
            state["initial_objective"] = new_objective

        objective = state["initial_objective"]
        structured_model = self.model.with_structured_output(Plan)

        progress = state.get("progress") or []
        if progress:
            # Re-plan: add only additional steps
            objective = state["messages"][-1]
            current_plan = state["plan"]

            step_conclusions = [sr[-1] for _, sr in progress]
            base_prompt = (
                f"Your objective was this: {objective.content}\n\n"
                f"Your original plan was this: {current_plan}\n\n"
                "The previous steps were not sufficient to fully meet the objective. "
                "Carefully analyze the gaps and propose only the additional steps necessary to achieve the goal. "
                "Each new step should be clear and focused, containing only the essential information needed. "
                "Ensure that no superfluous steps or details are added. "
                "The final step should directly lead to the objective being met and provide the final answer."
            )

            if self.experts:
                experts_list = "\n".join([str(expert) for expert in self.experts.values()])
                prompt = (
                    f"{base_prompt}\nHere is a list of experts with the new plan:\n{experts_list}\n\n"
                    "Using their expertise, develop clear and simple additional steps. "
                    "Only include steps that are absolutely necessary to achieve the objective. "
                    "The final step must directly lead to the correct answer.\n\n"
                )
            else:
                prompt = base_prompt

            messages = step_conclusions + [HumanMessage(content=prompt)]
            re_plan_result = await structured_model.ainvoke(messages)
            re_plan: Plan = re_plan_result if isinstance(re_plan_result, Plan) else Plan.model_validate(re_plan_result)

            thought = mk_thought(
                label="replan",
                node="replan",
                task="planning",
                content=str(re_plan),
            )

            return {
                "messages": [thought],
                "plan": Plan(steps=state["plan"].steps + re_plan.steps),
                "traces": ["Plan adjusted with additional steps."],
                "objective": objective,
            }

        # Initial plan
        else:
            objective = state["messages"][-1]
            base_prompt = (
                "For the given objective, come up with a clear and simple step-by-step plan. "
                "Each task should directly contribute to solving the objective. "
                "Avoid adding unnecessary steps or explanations. "
                "The final step must provide the correct answer. "
                "Ensure that each step includes all the information needed to proceed to the next step, without skipping key details."
            )

            if self.experts:
                experts_list = "\n".join([str(expert) for expert in self.experts.values()])
                prompt = (
                    "Here is a list of experts that can help you with your question:\n"
                    f"{experts_list}\n\n"
                    "Using their expertise, develop a clear and simple plan. "
                    "Only include tasks that are absolutely necessary to achieve the objective. "
                    "The final step must directly lead to the correct answer.\n\n"
                    f"{base_prompt}"
                )
            else:
                prompt = base_prompt

            messages = state["messages"] + [SystemMessage(content=prompt)]
            new_plan_result = await structured_model.ainvoke(messages)
            new_plan: Plan = new_plan_result if isinstance(new_plan_result, Plan) else Plan.model_validate(new_plan_result)

            thought = mk_thought(
                label="plan",
                node="plan",
                task="planning",
                content=str(new_plan),
            )

            return {
                "messages": [thought],
                "plan": new_plan,
                "traces": ["Initial plan set."],
                "progress": [],
                "objective": objective,
            }

    async def supervise(self, state: State):
        # Light progress marker for the UI
        return {"messages": [mk_thought(label="supervise", node="supervise", task="orchestration", content="Supervising…")]}

    async def execute(self, state: State):
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")
        progress = state.get("progress") or []
        task = state["plan"].steps[len(progress)]
        task_number = len(progress) + 1

        if not self.experts:
            raise ValueError("No experts available to execute the task.")

        # Thought: picking an expert
        picking = mk_thought(
            label="expert_select",
            node="execute",
            task="routing",
            content=f"Selecting the best expert for step {task_number}: {task}",
        )

        all_experts_info = "\n".join(
            f"{name}: {expert.description} (Categories: {', '.join(expert.categories)})"
            for name, expert in self.experts.items()
        )

        expert_prompt = (
            f"For the following plan:\n\n{state['plan']}\n\n"
            f"Which expert should execute step {task_number}, {task}?\n"
            "Here is a list of experts together with their capabilities and categories:\n"
            f"{all_experts_info}\n\n"
            "Please answer with **only the expert name** that is best suited to execute this task."
        )

        structured_model = self.model.with_structured_output(ExecuteDecision)
        raw = await structured_model.ainvoke([HumanMessage(content=expert_prompt)])

        # normalize + validate
        selected_raw = getattr(raw, "expert", None) or getattr(raw, "get", lambda *_: None)("expert")
        selected_expert = _normalize_choice(selected_raw or "", list(self.experts.keys()))

        decided = mk_thought(
            label="expert_selected",
            node="execute",
            task="routing",
            content=f"Selected expert: {selected_expert}",
            extras={"expert": selected_expert, "step": task_number, "task": str(task)},
        )

        logger.info("Fred selected expert: %s for step %s", selected_expert, task_number)

        if selected_expert not in self.experts:
            logger.warning("Expert %s is no longer available. Replanning...", selected_expert)
            # mark the failure as a thought for observability, then replan
            fail = mk_thought(
                label="expert_missing",
                node="execute",
                task="routing",
                content=f"Expert {selected_expert} missing. Replanning…",
            )
            plan_update = await self.plan(state)
            # prepend the failure thought to messages
            plan_update["messages"] = [fail] + (plan_update.get("messages") or [])
            return plan_update

        compiled_expert_graph = self.compiled_expert_graphs.get(selected_expert)
        if not compiled_expert_graph:
            logger.error("Expert %s missing compiled graph; triggering replanning.", selected_expert)
            fail = mk_thought(
                label="expert_graph_missing",
                node="execute",
                task="routing",
                content=f"Compiled graph not found for expert {selected_expert}. Replanning…",
            )
            plan_update = await self.plan(state)
            plan_update["messages"] = [fail] + (plan_update.get("messages") or [])
            return plan_update

        # Execute the task with the selected expert
        task_job = (
            f"For the following plan:\n\n{state['plan']}\n\n"
            f"You are tasked with executing step {task_number}, {task}."
        )

        step_conclusions = [sr[-1] for _, sr in progress]
        messages = step_conclusions + [SystemMessage(content=task_job)]
        response = await compiled_expert_graph.ainvoke({"messages": messages})

        # enrich expert messages so the UI can group them as execution thoughts
        expert_description = self.experts[selected_expert].description
        additional_messages: list[BaseMessage] = [picking, decided]
        for message in response.get("messages", []):
            new_message: BaseMessage = message
            md = _ensure_metadata_dict(new_message)
            # keep their existing metadata and add our execution context
            exec_extras = md.get("extras") or {}
            exec_extras.update(
                {
                    "node": "execute",
                    "task": str(task),
                    "task_number": task_number,
                    "agentic_flow": selected_expert,
                    "expert_description": expert_description,
                }
            )
            md["extras"] = exec_extras
            # mark as a thought if not already a final/answer-like message
            md.setdefault("thought", f"Execution output from {selected_expert}")
            new_message.response_metadata = md
            additional_messages.append(new_message)

        return {
            "messages": additional_messages,
            "traces": [f"Step {task_number} ({task}) assigned to {selected_expert} and executed"],
            "progress": (state.get("progress") or []) + [(task, response.get("messages", []))],
        }

    async def validate(self, state: State):
        if not self.model:
            raise ValueError("Model is not initialized. Call async_init first.")
        progress = state.get("progress") or []
        max_steps = self.max_steps if self.max_steps is not None else 0
        if max_steps and len(progress) >= max_steps:
            logger.warning(
                "Validation triggered by max_steps=%s — skipping LLM validation and forcing respond.",
                self.max_steps,
            )
            note = mk_thought(
                label="validate_forced",
                node="validate",
                task="gate",
                content=f"Reached max_steps={self.max_steps}. Forcing final response.",
            )
            return {"messages": [note], "plan_decision": PlanDecision(action="respond"), "traces": [f"Forced respond due to max_steps={self.max_steps}"]}

        objective = state["messages"][0].content
        current_plan = state["plan"]
        prompt = (
            f"Your objective was this: {objective}\n\n"
            f"Your original plan was this: {current_plan}\n\n"
            "The previous messages are the result of your reflexion for every step of the plan. "
            "You need to validate if the objective has been met after all this reflexion. "
            "If the objective has been fully achieved, respond with 'respond'. "
            "If additional steps are still required to meet the objective, respond with 'planning'. "
            "However, if you determine that the current plan cannot meet the objective given the available resources and experts, "
            "and further planning would not help, respond with 'respond'. "
            "If you are not absolutely sure more planning is needed, respond with 'respond'."
        )

        progress_msg = mk_thought(label="validate", node="validate", task="gate", content="Validating whether to respond or replan…")

        step_conclusions = [sr[-1] for _, sr in progress]
        messages = step_conclusions + [HumanMessage(content=prompt)]

        structured_model = self.model.with_structured_output(PlanDecision)
        plan_decision_result = await structured_model.ainvoke(messages)
        plan_decision: PlanDecision = (
            plan_decision_result if isinstance(plan_decision_result, PlanDecision) else PlanDecision.model_validate(plan_decision_result)
        )

        decided_msg = mk_thought(
            label="validate_decision",
            node="validate",
            task="gate",
            content=f"Decision: {plan_decision.action}",
        )

        return {"messages": [progress_msg, decided_msg], "plan_decision": plan_decision, "traces": [f"Evaluation done, status is {plan_decision}."]}
