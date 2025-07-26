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
import logging
from app.common.structures import AgentSettings
from app.model_factory import get_model
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from app.core.agents.flow import AgentFlow
from app.core.monitoring.node_monitoring.monitor_node import monitor_node

logger = logging.getLogger(__name__)
class GeneralistExpert(AgentFlow):
    """
    Generalist Expert provides guidance on a wide range of topics 
    without deep specialization. 
    """

    # Class-level attributes for metadata
    name: str = "GeneralistExpert"
    role: str = "Generalist Expert"
    nickname: str = "Georges"
    description: str = "Provides guidance on a wide range of topics without deep specialization."
    icon: str = "generalist_agent"
    categories: list[str] = []
    tag: str = "Generalist"
    
    def __init__(self, agent_settings: AgentSettings):     
        """
        Initializes the Generalist Expert agent.

        Args:
            cluster_fullname (str): The full name of the Kubernetes cluster 
                                    in the current context.
        """
        # Get agent settings
        self.agent_settings = agent_settings
        
        # Extract categories
        self.categories = agent_settings.categories if agent_settings.categories else ["General"]

        # Tell the Agent who it is via its base prompt
        self.base_prompt = self._generate_prompt()
        
        # Initialize parent class
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag
        )

    def _generate_prompt(self) -> str:
        lines = [
            "You are a friendly generalist expert, skilled at providing guidance on a wide range of topics without deep specialization.",
        ]
    
        lines += [
            "Your role is to respond with clarity, providing accurate and reliable information.",
            "When appropriate, highlight elements that could be particularly relevant.",
            f"The current date is {datetime.now().strftime('%Y-%m-%d')}.",
            "In case of graphical representation, render mermaid diagrams code.",
            "",
        ]
        return "\n".join(lines)

    async def expert(self, state: MessagesState):
        """
        Processes user messages and interacts with the model.

        Args:
            state (MessagesState): The current state of the conversation.

        Returns:
            dict: The updated state with the expert's response.
        """
        model = get_model(self.agent_settings.model)
        prompt = SystemMessage(content=self.base_prompt)
        response = await model.ainvoke([prompt] + state["messages"])
        return {"messages": [response]}

    def get_graph(self) -> StateGraph:
        """
        Defines the agentic flow graph for the expert.

        Returns:
            StateGraph: The constructed state graph.
        """
        builder = StateGraph(MessagesState)
        builder.add_node("expert", monitor_node(self.expert))
        builder.add_edge(START, "expert")
        builder.add_edge("expert", END)
        return builder