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

from datetime import datetime
from typing import Optional, override

from langchain_core.messages import HumanMessage
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from flow import AgentFlow
from agents.keda.structures import KedaScaling, MessagesStateWithFinalStructuredResponse
from agents.keda.keda_toolkit import KedaToolkitBuilder
from fred.application_context import get_app_context


class KedaExpert(AgentFlow):
    """
    An expert that provides KEDA configurations, which Kubernetes uses to specify how KEDA should scale
    a target application based on defined triggers (e.g., cron-based scaling or Prometheus-based scaling).
    The expert interprets facts about the application to make assumptions and propose a KEDA configuration.
    """
    # Class-level attributes for metadata
    name: str = "KedaExpert"
    role: str = "KEDA Expert"
    nickname: str = "Kaden"
    description: str = "Provides KEDA configurations for Kubernetes autoscaling."
    icon: str = "keda_agent"
    categories: list[str] = []
    tag: str = "Frugal IT"  # Défini au niveau de la classe

    def __init__(self, cluster_fullname: Optional[str], kube_service):
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Obtenir les paramètres de configuration de l'agent
        try:
            from fred.application_context import get_agent_settings
            agent_settings = get_agent_settings(self.name)
            categories = agent_settings.categories if agent_settings.categories else []
            # On conserve le tag de classe si agent_settings.tag est None ou vide
            if agent_settings.tag:
                self.tag = agent_settings.tag
        except:
            categories = []
            
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=(
                "An expert that provides KEDA configurations, which Kubernetes uses to specify how KEDA should scale "
                "a target application based on defined triggers (e.g., cron-based scaling or Prometheus-based scaling). "
                "The expert interprets facts about the application to make assumptions and propose a KEDA configuration."
            ),
            icon=self.icon,
            base_prompt=(
                f"Your current context involves a Kubernetes cluster named {self.cluster_fullname}.\n" if self.cluster_fullname else ""
                f"The current date is {current_date}.\n"
                "You are an assistant that processes functional descriptions to generate "
                "KEDA cron configurations or KEDA Prometheus-based scaling configurations. "
                "Each type of KEDA configuration has its specific tool for generation. "
                "Your tasks are:\n\n"
                "    * Interpret functional descriptions (e.g., 'ingestion during business hours' or "
                "'scale based on HTTP request count') to extract parameters such as start/end cron, "
                "namespace, configuration_name, target_name, target_kind, desired_replicas, metric, "
                "query, min_replicas, max_replicas, and threshold. "
                "If some parameters are missing, make assumptions based on the following guidelines:\n\n"
                "    * Generate a **valid KEDA ScaledObject JSON** if the description involves scheduled scaling or Prometheus-based scaling. "
                "The output should always be a **fully-formed KEDA ScaledObject** (Kubernetes Custom Resource Definition in JSON format), not just key-value parameters.\n\n"
                "Guidelines:\n\n"
                "    * When making assumptions, first look at the cluster's Kube configuration (e.g., "
                "ConfigMaps, services, and other relevant resources) to extract context-specific details "
                "that can be inferred. Use this data to fill in missing parameters.\n"
                "    * If information cannot be derived from the Kube configuration, use best practices to make assumptions, "
                "ensuring the configuration is both robust and frugal. For example, assume conservative values for replicas "
                "to avoid over-provisioning.\n"
                "    * Compute the most efficient desired replicas based on the available target resource information, "
                "balancing efficiency and performance.\n"
                "    * If the time zone is not specified, default to UTC unless the cluster's region indicates otherwise.\n"
                "    * For vague descriptions (e.g., 'business hours'), infer the relevant values (e.g., time, time zone), "
                "and generate the configuration accordingly. Be sure to list all assumptions clearly for the user.\n"
                "    * **ALWAYS return the corresponding KEDA JSON configuration (ScaledObject from the appropriate tool)** "
                "based on the assumptions. If there are assumptions, return them as a list.\n"
                "    * Do not ask for confirmation without proposing a **valid KEDA ScaledObject JSON** configuration with the inferred parameters.\n"
                "    * Ask for missing details **only** if you cannot make assumptions from the Kube configuration or best practices, "
                "and only when essential parameters like namespace, time specifications, metrics, etc., are completely missing.\n"
                "    * Reject out-of-scope requests (e.g., unrelated tasks or services) and politely explain the app's limitations.\n\n"
            ),
            categories=categories,
            tag=self.tag,
            graph=self.get_graph(),
            toolkit=KedaToolkitBuilder(kube_service).build(),
        )
        self.cluster_fullname = cluster_fullname
        llm = get_app_context().get_model_for_agent("KedaExpert")
        self.llm_with_structured_output = llm.with_structured_output(KedaScaling, method="function_calling")
        self.llm_with_tools = llm.bind_tools(self.toolkit.get_tools())

    async def reasoner(self, state: MessagesStateWithFinalStructuredResponse):
        return {"messages": [self.llm_with_tools.invoke([self.base_prompt] + state["messages"])]}

    # Define the function that responds to the user
    async def respond(self, state: MessagesStateWithFinalStructuredResponse):
        # We call the model with structured output to return the same format to the user every time
        # state['messages'][-2] is the last ToolMessage in the convo.
        # We convert the final AI message to a HumanMessage for the model to use.
        response: KedaScaling = self.llm_with_structured_output.invoke(
            [HumanMessage(content=state["messages"][-1].content)]
        )
        # We return the final answer
        return {
            "final_response": response
        }

    # Function on the edges
    # Define the function that determines whether to continue or not
    @staticmethod
    async def should_continue(state: MessagesStateWithFinalStructuredResponse):
        messages = state["messages"]
        last_message = messages[-1]
        # If there is no function call, then we respond to the user
        if not last_message.tool_calls:
            return "respond"
        # Otherwise if there is, we continue
        else:
            return "continue"

    @override
    def get_graph(self) -> StateGraph:
        builder = StateGraph(MessagesStateWithFinalStructuredResponse)

        # Add nodes
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("respond", self.respond)
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

        # Add edges: performing a loop "while we need to call a tool"
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner",
            self.should_continue,
            {
                "continue": "tools",
                "respond": "respond",
            },
        )
        builder.add_edge("tools", "reasoner")
        builder.add_edge("respond", END)

        return builder