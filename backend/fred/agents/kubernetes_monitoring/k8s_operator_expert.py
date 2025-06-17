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
from typing import Optional

from fred.flow import AgentFlow
from langgraph.graph import MessagesState, StateGraph
from langgraph.constants import START
from langgraph.prebuilt import ToolNode, tools_condition

from fred.application_context import get_agent_settings, get_model_for_agent, get_mcp_client_for_agent
from fred.agents.kubernetes_monitoring.k8s_operator_toolkit import K8SOperatorToolkit

class K8SOperatorExpert(AgentFlow):
    """
    Expert to execute actions on a Kubernetes cluster.
    """
    # Class-level attributes for metadata
    name: str = "K8SOperatorExpert"
    role: str = "Kubernetes Operator Expert"
    nickname: str = "Kimberley"
    description: str = (
        "A Kubernetes monitoring & operator expert that can perform various actions on a Kubernetes cluster "
        "to provide insights on cluster performance, state of the current installed resources, "
        "pod status, container information, logs, and many more. This expert performs the relevant "
        "kubectl and helm commands in order to fulfill its mission and generate meaningful "
        "and aggregated results for the user."
    )
    icon: str = "k8s_operator_agent"
    categories: list[str] = []
    tag: str = "k8s operator"  # Défini au niveau de la classe
    
    def __init__(self, 
                 cluster_fullname: Optional[str]
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.cluster_fullname = cluster_fullname
        self.agent_settings = get_agent_settings(self.name)
        self.model = get_model_for_agent(self.name)
        self.mcp_client = get_mcp_client_for_agent(self.name)
        self.toolkit = K8SOperatorToolkit(self.mcp_client)
        self.model_with_tools = self.model.bind_tools(self.toolkit.get_tools())
        self.llm = self.model_with_tools
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["Operator"]
        # On conserve le tag de classe si agent_settings.tag est None ou vide
        if self.agent_settings.tag:
            self.tag = self.agent_settings.tag

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self._generate_prompt(),
            categories=self.categories,
            tag=self.tag,
        )
        

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Kubernetes operator expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        lines = [
            "You are a Kubernetes monitoring & operator expert with access to tools for retrieving and analyzing data.",
        ]
        if self.cluster_fullname:
            lines.append(f"Your current context involves a Kubernetes cluster named {self.cluster_fullname}, and you are equipped with MCP server tools.")
        else:
            lines.append("You are equipped with MCP server tools.")

        lines += [
            "",
            "### Your Primary Responsibilities:",
            "1. **Retrieve Data**: Use the provided tools, including MCP server tools, to fetch data for:",
            "   - Pods & containers statuses and logs.",
            "   - The state of the deployed resources and whether they are functioning properly.",
            "   - Retrieve any malfunction in the cluster.",
            "2. **Aggregate Data**: Execute appropriate commands using the MCP server in order to:",
            "   - Get and interpret the logs and the resource statuses.",
            "   - Summarize key insights in a user-friendly manner.",
            "",
            "### Key Instructions:",
            "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.",
            "2. Aggregate and analyze the data to directly answer the user's query.",
            "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.",
            "",
            f"The current date is {datetime.now().strftime('%Y-%m-%d')}.",
            "",
        ]
        return "\n".join(lines)

    
    async def reasoner(self, state: MessagesState):
        response = self.llm.invoke([self.base_prompt] + state["messages"])

        return {"messages": [response]}

    def get_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder