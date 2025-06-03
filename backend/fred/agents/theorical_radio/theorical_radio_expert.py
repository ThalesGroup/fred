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

from common.structure import AgentSettings
from flow import AgentFlow
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agents.theorical_radio.theorical_radio_toolkit import TheoricalRadioToolkit
from fred.application_context import get_agent_settings, get_model_for_agent

class TheoricalRadioExpert(AgentFlow):
    """
    Expert to provide guidance on theorical radio/signal data.
    """
    # Class-level attributes for metadata
    name: str = "TheoricalRadioExpert"
    role: str = "Radio Expert"
    nickname: str = "Romeo"
    description: str =(
                "An expert that knows all of the information on theoretical radio data. It can "
                "provide a summary and analyze them. The data it works with originate from a "
                "signal/radio identification guide or wiki that contains factual data that "
                "reprensent the many various signals present in the world around us. These can"
                "be civil, military or any other. This expert retrieves raw data in JSON format, "
                " processes it, and generates meaningful aggregated results for the user."
            )
    icon: str = "theorical_radio_agent"
    
    def __init__(self, 
                 cluster_fullname: Optional[str],
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit=TheoricalRadioToolkit()
        self.cluster_fullname = cluster_fullname
        self.model = get_model_for_agent(self.name)
        self.model_with_tools = self.model.bind_tools(self.toolkit.get_tools())
        self.llm = self.model_with_tools
        self.agent_settings = get_agent_settings(self.name)
        categories = self.agent_settings.categories if self.agent_settings.categories else ["theorical_radio"]
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self._generate_prompt(),
            categories=categories,
            toolkit=self.toolkit 
        )
        

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Theorical radio data expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
                "You are an operational expert with access to tools for retrieving and analyzing factual radio data."
                "These data originate from a provided CSV file which is a signal identification wiki. "
                "These are actual information on different types of signals that exist.\n\n"
                "### Your Primary Responsibilities:\n"
                "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
                "   - Radio signal use.\n"
                "   - Get a factual overview of common radio/signal data that exist in the world.\n"
                "   - Ship name and missions\n"
                "2. **Aggregate Data**: Process the raw data you retrieve by:\n"
                "   - Aggregating data to be used by another agent in order to enlarge its scope.\n"
                "   - Summarizing key insights in a user-friendly manner.\n\n"
                "### Key Instructions:\n"
                "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.\n"
                "2. Aggregate and analyze the data to directly answer the user's query.\n"
                "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.\n\n"
                f"The current date is {self.current_date}.\n\n"
                f"Your current context involves a Kubernetes cluster named {self.cluster_fullname}.\n" if self.cluster_fullname else ""
            )

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
