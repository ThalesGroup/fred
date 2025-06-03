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

from flow import AgentFlow
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agents.theater_analysis.theater_analysis_toolkit import TheaterAnalysisToolkit
from fred.application_context import get_agent_settings, get_model_for_agent

class TheaterAnalysisExpert(AgentFlow):
    """
    Expert to provide guidance on ship location.
    """
    # Class-level attributes for metadata
    name: str = "TheaterAnalysisExpert"
    role: str = "Theater of Operations Analysis Expert"
    nickname: str = "Tango"
    description: str =(
                "A Ship expert that retrieves raw data from a live theater of operations (via sensor data) and performs aggregation "
                "to provide insights on the field as well a tactical information. It is specifically made for analyzing data from actual sensors."
                "This expert retrieves raw data in JSON format, processes it, "
                "and generates meaningful aggregated results for the user."
            )
    icon: str = "ship_location_agent"
    
    def __init__(self, 
                 cluster_fullname: Optional[str],
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit=TheaterAnalysisToolkit()
        self.cluster_fullname = cluster_fullname
        self.model = get_model_for_agent(self.name)
        self.model_with_tools = self.model.bind_tools(self.toolkit.get_tools())
        self.llm = self.model_with_tools
        self.agent_settings = get_agent_settings(self.name)
        categories = self.agent_settings.categories if self.agent_settings.categories else ["ship_location"]
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
        Generates the base prompt for the Ship Location expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
                "You are a expert that is able to determine a ship location based on the radio protocol it uses "
                "with access to tools for retrieving and analyzing data. "
                "The expert can also retrieve information on the sensor data that denotate."
                "from the information provided in the CSV files.\n\n"
                "### Your Primary Responsibilities:\n"
                "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
                "   - Detecting abnormalities in ship location.\n"
                "   - Detect when a ship is not supposed to be located where it is.\n"
                "   - Ship radio frequencies used for communication as well as protocol used.\n"
                "2. **Aggregate Data**: Process the raw data you retrieve by:\n"
                "   - Calculating and identifying abnormalities.\n"
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
    
