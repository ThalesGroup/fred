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
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import END, START, MessagesState, StateGraph
from flow import AgentFlow
from agents.technical_kubernetes.technical_kubernetes_toolkit import (
    TechnicalKubernetesToolkitBuilder,
)
from fred.application_context import get_agent_settings, get_model_for_agent
from fred.services.ai.ai_service import AIService
from fred.services.kube.kube_service import KubeService
from model_factory import get_model

class TechnicalKubernetesExpert(AgentFlow):
    """
    Expert to provide technical guidance on Kubernetes.
    """

    # Class-level attributes for metadata
    name: str = "TechnicalKubernetesExpert"
    role: str = "Technical Kubernetes Expert"
    nickname: str = "Ethan"
    description: str = "Provides precise technical insights about a Kubernetes cluster."
    icon: str = "kubernetes_agent"
    categories: list[str] = []
    tag: str = "Warfare"

    def __init__(self, 
                 cluster_fullname: str
                 ):
        """
        Initializes the Kubernetes expert agent.

        Args:
            cluster_fullname (str): The full name of the Kubernetes cluster in the current context.
            ai_service: The AI service used for tool-based interactions.
        """
        self.agent_settings = get_agent_settings(self.name)
        self.cluster_fullname = cluster_fullname
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        kube_service = KubeService()
        ai_service = AIService(cluster_fullname, kube_service)
        self.toolkit = TechnicalKubernetesToolkitBuilder(ai_service).build()
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["Kubernetes"]
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self._generate_prompt(),
            categories=self.categories,
            toolkit=self.toolkit,
            tag=self.tag, 
        )

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Kubernetes expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
            "You are a friendly technical Kubernetes expert.\n"
            f"The cluster you are in charge of is named {self.cluster_fullname}.\n"
            "Your role is to provide clear and precise technical guidance about this cluster.\n"
            "You have access to a set of tools to retrieve specific information about the cluster.\n"
            "When needed, highlight your technical and operational knowledge in your response.\n"
            f"The current date is {self.current_date}.\n"
            "If a graphical representation is required, use Mermaid diagrams.\n\n"
        )

    async def expert(self, state: MessagesState):
        """
        Processes user messages and interacts with the model.

        Args:
            state (MessagesState): The current state of the conversation.

        Returns:
            dict: The updated state with the expert's response.
        """
        model = get_model_for_agent(self.name)
        model_with_tools = model.bind_tools(self.toolkit.get_tools())

        prompt = SystemMessage(content=self.base_prompt)
        response = await model_with_tools.ainvoke([prompt] + state["messages"])

        return {"messages": [response]}

    def get_graph(self) -> StateGraph:
        """
        Defines the agentic flow graph for the Kubernetes expert.

        Returns:
            StateGraph: The constructed state graph.
        """
        builder = StateGraph(MessagesState)
        builder.add_node("expert", self.expert)

        # Include toolkit usage if available
        if self.toolkit.get_tools():
            builder.add_node("tools", ToolNode(self.toolkit.get_tools()))
            builder.add_edge(START, "expert")
            builder.add_conditional_edges("expert", tools_condition)
            builder.add_edge("tools", "expert")
        else:
            builder.add_edge(START, "expert")

        builder.add_edge("expert", END)
        return builder
