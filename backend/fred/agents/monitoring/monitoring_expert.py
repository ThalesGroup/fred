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
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from fred.agents.monitoring.monitoring_toolkit import MonitoringToolkit
from fred.application_context import get_agent_settings, get_model_for_agent
from fred.monitoring.node_monitoring.monitor_node import monitor_node


class MonitoringExpert(AgentFlow):
    """
    Expert to provide guidance on Kubernetes monitoring.
    """
    # Class-level attributes for metadata
    name: str = "MonitoringExpert"
    role: str = "Monitoring Expert"
    nickname: str = "Maya"
    description: str = (
                "A Kubernetes monitoring expert specialized in live electricity consumption, energy mix (including carbon intensity and CO₂ emissions), financial costs, and sustainability insights. Maya can answer questions about Kubernetes clusters using both internal metrics and external environmental data such as public electricity mix databases."
            )
    icon: str = "monitoring_agent"
    categories: list[str] = []
    tag: str = "Frugal IT"  # Défini au niveau de la classe
    
    def __init__(self, 
                 cluster_fullname: Optional[str]
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit = MonitoringToolkit()
        self.cluster_fullname = cluster_fullname
        self.agent_settings = get_agent_settings(self.name)
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["Monitoring"]
        self.base_prompt=self._generate_prompt()
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
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
            toolkit=self.toolkit 
        )
        

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Kubernetes expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        lines = [
            "You are a Kubernetes monitoring expert with access to tools for retrieving and analyzing data.",
        ]
        if self.cluster_fullname:
            lines.append(f"Your current context involves a Kubernetes cluster named {self.cluster_fullname}.")

        lines += [
            "",
            "### Your Primary Responsibilities:",
            "1. **Retrieve Data**: Use the provided tools to fetch data for:",
            "   - Energy consumption (grouped by namespace).",
            "   - Energy and electricity mix for the region where the cluster resides.",
            "   - Financial costs (e.g., compute, storage, and network expenses).",
            "2. **Aggregate Data**: Process the raw data you retrieve by:",
            "   - Calculating totals, averages, and trends.",
            "   - Summarizing key insights in a user-friendly manner.",
            "",
            "### Key Instructions:",
            "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.",
            "2. Aggregate and analyze the data to directly answer the user's query.",
            "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.",
            "",
            f"The current date is {datetime.now().strftime('%Y-%m-%d')}.",
            "",
            "### Example Queries and Outputs:",
            "- Query: 'What was the energy consumption for the cluster last week?'",
            "  - Fetch the raw data using the energy consumption tool.",
            "  - Aggregate by namespace and calculate the weekly total and daily average.",
            "  - Present results in this format:",
            "    ```json",
            "    {",
            "        'total_energy_consumption': '500 kWh',",
            "        'daily_average': '71.43 kWh',",
            "        'namespace_breakdown': {",
            "            'namespace1': '200 kWh',",
            "            'namespace2': '300 kWh'",
            "        }",
            "    }",
            "    ```",
            "- Query: 'How much did the cluster cost last week?'",
            "  - Use the financial consumption tool to get raw cost data.",
            "  - Calculate the weekly total and average daily cost.",
            "  - Include a breakdown by components (e.g., compute, storage, network).",
            "  - Present results in a structured and concise format.",
        ]
        return "\n".join(lines)
    
    def get_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", monitor_node(self.reasoner))
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder