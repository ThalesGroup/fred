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
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.state import END, START, CompiledStateGraph, StateGraph

from flow import AgentFlow, Flow
from fred.application_context import get_model_for_leader
from model_factory import get_model
from leader.structures.decision import ExecuteDecision, PlanDecision
from leader.structures.plan import Plan
from leader.structures.state import State
logger = logging.getLogger(__name__)

MAX_STEPS = 5

class Leader(Flow):
    """
    Fred is an agentic flow chatbot that uses a plan and supervisor approach with ReAct experts calling.
    It manages a dynamic list of experts that can be updated during the session.
    """

    name: str = "Fred"
    role: str = "Team Leader"
    nickname: str = "Fred"
    description: str = "Supervises multiple experts to provide answers and insights."
    icon: str = "fred_agent"
    tag: str = "leader"

    def __init__(self,):
        
        """
        Initializes Fred 
        """
        super().__init__(
            name=self.name,
            description=(
                "Fred is an agentic flow chatbot "
                "that uses a plan and supervisor approach with ReAct experts calling."
            ),
            graph=None,
        )

        self.graph = None # the graph is built only when we need it, after the method are available
        self.model = get_model_for_leader()
        self.experts: dict[str, AgentFlow] = {}
        self.compiled_expert_graphs: dict[str, CompiledStateGraph] =  {}
        self.graph = self.get_graph()

    def reset_experts(self):
        """
        Reset the list of experts.
        """
        logger.info(f"Resetting Fred experts. Previous experts: {list(self.experts.keys())}")
        self.experts = {}
        self.compiled_expert_graphs = {}

    def add_expert(self, name, instance, compiled_graph):
        """
        Add an expert to Fred.

        Args:
            name (str): The name of the expert.
            compiled_graph (CompiledStateGraph): The compiled graph of the expert.
        """
        self.experts[name] = instance
        self.compiled_expert_graphs[name] = compiled_graph

    def get_graph(self) -> StateGraph:
        """
        Defines Fred's agentic flow.
        """
        if self.graph is None:
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
            logger.info(f"created new Fred graph: {self.graph}")
            self.graph = builder
        logger.info(f"reusing Fred graph: {self.graph}")
        return self.graph

    async def should_validate(self, state: State) -> Literal["execute", "validate"]:
        """
        Check if the agent should validate the current state.

        Args:
            state: State of the agent.
        """
        if len(state["progress"]) >= MAX_STEPS:
            logger.warning(f"Reached MAX_STEPS={MAX_STEPS}, forcing final answer.")
            return "validate"
        if len(state["progress"]) == len(state["plan"].steps):
            return "validate"
        return "execute"

    async def should_replan(self, state: State) -> Literal["respond", "planning"]:
        """
        Check if the agent should re-plan the current state.

        Args:
            state: State of the agent.
        """
        if state["plan_decision"].action == "planning":
            return "planning"

        return "respond"

    async def respond(self, state: State):
        """
        Respond to the user.

        Args:
            state: State of the agent.
        """

        step_conclusions_str = ""
        for _, step_responses in state["progress"]:
            step_conclusions_str += f"{step_responses[-1].content}\n"

        prompt = (
            f"In your responses you will only use data retrieved from the different agents.\n"
            f"Some of your agents are theorical which means that for a live data analysis you need to avoid querying them.\n"
            f"You executed this plan:\n"
            f"{state['plan']}\n"
            f"For each step you came up with the following conclusions:\n"
            f"{step_conclusions_str}\n"
            f"Given all these conclusions, what is your final answer to the quesion :"
            f"{state['objective']}"
        )

        # Given the output of each step 'step_conclusions', I ask my question 'state["objective"]'
        messages = [HumanMessage(content=prompt)]

        response = await self.model.ainvoke(messages)

        return {
            "messages": [response],
            "traces": ["Responded to the user."],
        }

    async def plan(self, state: State):
        """
        Plan the steps to follow.

        Args:
            state: State of the agent.
        """
        new_objective = None
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                new_objective = message
                break

        if new_objective is None:
            raise ValueError("No human message found for objective.")
        
        # Initialize initial_objective if it doesn't exist
        if "initial_objective" not in state:
            state["progress"] = []  # Clear previous progress
            state["plan"] = None    # Reset the plan
            state["initial_objective"] = new_objective

        # Use the stored initial_objective for comparison
        if state["initial_objective"].content != new_objective.content:
            logger.info("New initial objective detected. Resetting plan and progress.")
            state["progress"] = []  # Clear previous progress
            state["plan"] = None    # Reset the plan
            state["initial_objective"] = new_objective

        # Then use state["initial_objective"] in your prompts instead of state["objective"]
        objective = state["initial_objective"]

        structured_model = self.model.with_structured_output(Plan)

        # If some progress has been made, the agent needs to come up with additional steps.
        if "progress" in state and len(state["progress"]) > 0:
            objective = state["messages"][-1]
            current_plan = state["plan"]

            step_conclusions = []
            for _, step_responses in state["progress"]:
                step_conclusions.append(step_responses[-1])

            base_prompt = (
                f"Your objective was this: {objective.content}\n\n"
                f"Your original plan was this: {current_plan}\n\n"
                f"The previous steps were not sufficient to fully meet the objective. "
                f"Carefully analyze the gaps and propose only the additional steps necessary to achieve the goal. "
                f"Each new step should be clear and focused, containing only the essential information needed. "
                f"Ensure that no superfluous steps or details are added. "
                f"The final step should directly lead to the objective being met and provide the final answer."
            )

            if self.experts and len(self.experts) > 0:
                experts_list = "\n".join([str(expert) for expert in self.experts])
                expert_prompt = (
                    f"{base_prompt}"
                    f"Here is a list of experts with the new plan:\n"
                    f"{experts_list}\n\n"
                    f"Using their expertise, develop a clear and simple additional steps. "
                    f"Only include steps that are absolutely necessary to achieve the objective. "
                    f"The final step must directly lead to the correct answer.\n\n"
                )
                prompt = expert_prompt
            else:
                prompt = base_prompt

            messages = step_conclusions + [HumanMessage(content=prompt)]
            re_plan: Plan = await structured_model.ainvoke(messages)

            # Add additional messages to the messages with metadata
            # Include the user and plan messages
            additional_messages: list[BaseMessage] = [
                AIMessage(
                    content=str(re_plan),
                    response_metadata={
                        "thought": True,
                        "fred": {
                            "node": "replan",
                            "task": "Refine the plan",
                        },
                    },
                )
            ]

            return {
                "messages": additional_messages,
                "plan": Plan(steps=state["plan"].steps + re_plan.steps),
                "traces": ["Plan adjusted with additional steps."],
                "objective": objective,
            }

        # If no progress has been made, the agent needs to come up with the initial plan.
        else:
            objective = state["messages"][-1]
            base_prompt = (
                "For the given objective, come up with a clear and simple step-by-step plan. "
                "Each task should directly contribute to solving the objective. "
                "Avoid adding unnecessary steps or explanations. "
                "The final step must provide the correct answer. "
                "Ensure that each step includes all the information needed to proceed to the next step, without skipping key details."
            )

            if self.experts and len(self.experts) > 0:
                experts_list = "\n".join([str(expert) for expert in self.experts])
                expert_prompt = (
                    f"Here is a list of experts that can help you with your question:\n"
                    f"{experts_list}\n\n"
                    f"Using their expertise, develop a clear and simple plan. "
                    f"Only include tasks that are absolutely necessary to achieve the objective. "
                    f"The final step must directly lead to the correct answer.\n\n"
                    f"{base_prompt}"
                )
                prompt = expert_prompt
            else:
                prompt = base_prompt

            messages = state["messages"] + [SystemMessage(content=prompt)]

            new_plan: Plan = await structured_model.ainvoke(messages)

            # Add additional messages to the messages with metadata
            # Include the user and plan messages
            additional_messages: list[BaseMessage] = [
                AIMessage(
                    content=str(new_plan),
                    response_metadata={
                        "thought": True,
                        "fred": {
                            "node": "plan",
                            "task": "Define the plan",
                        },
                    },
                ),
            ]
            return {
                "messages": additional_messages,
                "plan": new_plan,
                "traces": ["Initial plan set."],
                "progress": [],
                "objective": objective,
            }

    async def supervise(self, state: State):
        """
        Supervise the execution of the plan.
        """

        return {"traces": ["Supervising..."]}

    async def execute(self, state: State):
        """
        Proceed with the execution of the next step in the plan.

        Args:
            state: State of the agent.
        """

        # Get the task to execute
        task = state["plan"].steps[len(state["progress"])]
        task_number = len(state["progress"]) + 1

        if not self.experts or len(self.experts) == 0:
            raise ValueError("No experts available to execute the task.")

        all_experts_info = "\n".join(
        [f"{name}: {expert.description} (Categories: {', '.join(expert.categories)})"
         for name, expert in self.experts.items()]
        )
        # select the expert to execute the task
        # experts_list = "\n".join([str(expert) for expert in self.experts])
        expert_prompt = (
            f"For the following plan:\n\n"
            f"{state['plan']}\n\n"
            f"Which expert should execute step {task_number}, {task}?\n"
            f"Here is a list of experts together with their capabilites and categories that can help you with your question:\n"
            f"{all_experts_info}\n\n"
            f"Please answer with **only the expert name** that is best suited to execute this task."
        )
        structured_model = self.model.with_structured_output(ExecuteDecision)
        expert_decision = await structured_model.ainvoke(
            [HumanMessage(content=expert_prompt)]
        )
        selected_expert = expert_decision.expert
        logger.info(f"Fred selected expert: {selected_expert} for step {task_number}")
        if selected_expert not in self.experts:
            logger.warning(f"Expert {selected_expert} is no longer available. Replanning...")
            raise ValueError("No experts available to execute the task.")

        compiled_expert_graph = self.compiled_expert_graphs.get(selected_expert)
        if not compiled_expert_graph:
            logger.error(f"Expert {selected_expert} not found in compiled_expert_graphs.")
            return await self.plan(state)  # Trigger replanning

        # Execute the task
        task_job = (
            f"For the following plan:\n\n"
            f"{state['plan']}\n\n"
            f"You are tasked with executing step {task_number}, {task}."
        )

        step_conclusions = []
        for _, step_responses in state["progress"]:
            step_conclusions.append(step_responses[-1])

        messages = step_conclusions + [SystemMessage(content=task_job)]
        response = await compiled_expert_graph.ainvoke({"messages": messages})

        # Retrieve expert name and description

        for expert in self.experts.values():  # Iterate over the AgentFlow instances
            if expert.name == expert_decision.expert:
                expert_name = expert.name
                expert_description = expert.description
                break

        # Add additional messages to the messages with metadata
        # Include all progress messages for the current task
        additional_messages: list[BaseMessage] = []
        response_messages = response.get("messages", [])
        for message in response_messages:
            new_message: BaseMessage = message
            new_message.response_metadata.update(
                {
                    "thought": True,
                    "fred": {
                        "node": "execute",
                        "agentic_flow": expert_name,
                        "expert_description": expert_description,
                        "task_number": task_number,
                        "task": task,
                    },
                }
            )
            additional_messages.append(new_message)

        return {
            "messages": additional_messages,
            "traces": [
                f"Step {task_number} ({task}) assigned to {expert_name} and executed"
            ],
            "progress": state["progress"] + [(task, response.get("messages", []))],
        }

    async def validate(self, state: State):
        """
        Validate if the goal has been met following the current plan.

        Args:
            state: State of the agent.
        """

        if len(state["progress"]) >= MAX_STEPS:
            logger.warning(f"Validation triggered by MAX_STEPS={MAX_STEPS} — skipping LLM validation and forcing respond.")
            return {
                "plan_decision": PlanDecision(action="respond"),
                "traces": [f"Forced respond due to reaching MAX_STEPS={MAX_STEPS}"],
            }
        
        objective = state["messages"][0].content
        current_plan = state["plan"]

        prompt = (
            f"Your objective was this: {objective}\n\n"
            f"Your original plan was this: {current_plan}\n\n"
            f"The previous messages are the result of your reflexion for every step of the plan. "
            f"You need to validate if the objective has been met after all this reflexion. "
            f"If the objective has been fully achieved, respond with 'respond'. "
            f"If additional steps are still required to meet the objective, respond with 'planning'. "
            f"However, if you determine that the current plan cannot meet the objective given the available resources and experts, "
            f"and further planning would not help, respond with 'respond'. "
            f"If you are not absolutely sure more planning is needed, respond with 'respond'."
        )
        """ prompt = (
            f"Your objective was this: {objective}\n\n"
            f"Your original plan was this: {current_plan}\n\n"
            f"The previous messages are the result of your reflexion for every step of the plan. "
            f"You need to validate if the objective has been met after all this reflexion. "
            f"If the objective has been fully achieved, respond with 'respond'. "
            f"If additional steps are still required to meet the objective, respond with 'planning'. "
            f"However, if you determine that the current plan cannot meet the objective given the available resources and experts, "
            f"and further planning would not help, respond with 'respond'."
        ) """

        step_conclusions = []
        for _, step_responses in state["progress"]:
            step_conclusions.append(step_responses[-1])

        messages = step_conclusions + [HumanMessage(content=prompt)]

        structured_model = self.model.with_structured_output(PlanDecision)
        plan_decision: PlanDecision = await structured_model.ainvoke(messages)

        return {
            "plan_decision": plan_decision,
            "traces": [f"Evaluation done, status is {plan_decision}."],
        }
