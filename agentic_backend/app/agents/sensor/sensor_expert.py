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

from app.common.structure import AgentSettings
from app.flow import AgentFlow
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.sensor.sensor_toolkit import SensorToolkit
from app.application_context import get_agent_settings, get_model_for_agent

class SensorExpert(AgentFlow):
    """
    Expert to provide guidance on Sensor configuration.
    """
    # Class-level attributes for metadata
    name: str = "SensorExpert"
    role: str = "Sensor Expert"
    nickname: str = "Sim"
    description: str =(
                "A sensor expert knows how to perform a frequency sweep and return different frequency bands "
                "to provide insights on factual data. It has access to data describing factual data on maritime district, ship registration etc."
                "It is not relevant for analyzing actual sensor data from the Theater of operation on the sea but is rather a snapshot."
                "This expert retrieves raw data in JSON format, processes it, "
                "and generates meaningful aggregated results for the user."
            )
    icon: str = "sensor_agent"
    
    def __init__(self, 
                 cluster_fullname: Optional[str]
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit=SensorToolkit()
        self.cluster_fullname = cluster_fullname
        self.model = get_model_for_agent(self.name)
        self.base_prompt=self._generate_prompt()
        self.agent_settings = get_agent_settings(self.name)
        categories = self.agent_settings.categories if self.agent_settings.categories else ["sweep"]
        
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self.base_prompt,
            categories=categories,
            tag=self.agent_settings.tag, 
            toolkit=self.toolkit,
        )
        

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Sensor expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
                "You are a Sensor and war marine operation expert with access to tools for retrieving and analyzing data "
                "from the information provided in the CSV files.\n\n"
                "### Your Primary Responsibilities:\n"
                "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
                "   - Frequency Sweep \n"
                "2. **Aggregate Data**: Process the raw data you retrieve by:\n"
                "   - Calculating trajectories, radar/sensor, trends.\n"
                "   - Summarizing key insights in a user-friendly manner.\n\n"
                "### Key Instructions:\n"
                "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.\n"
                "2. Aggregate and analyze the data to directly answer the user's query.\n"
                "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.\n\n"
                f"The current date is {self.current_date}.\n\n"
            )

    async def reasoner(self, state: MessagesState):
        response = self.model.invoke([self.base_prompt] + state["messages"])

        return {"messages": [response]}

    def get_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(self.toolkit.get_tools()))

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder
