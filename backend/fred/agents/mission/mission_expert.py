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
from flow import AgentFlow
from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from agents.mission.mission_toolkit import MissionToolkit
from fred.application_context import get_agent_settings, get_model_for_agent

class MissionExpert(AgentFlow):
    """
    Expert to provide guidance on Mission planning.
    """
    # Class-level attributes for metadata
    name: str = "MissionExpert"
    role: str = "Mission Expert"
    nickname: str = "Mike"
    description: str = (
        "An expert that know all of the information on the ongoing mission. It can "
        "provide insights on the field as well a tactical information, active ships (or not) "
        "and know about the communication protocol the ships use."
        "This expert retrieves raw data in JSON format, processes it, "
        "and generates meaningful aggregated results for the user."
    )
    icon: str = "mission_agent"
    categories: list[str] = []
    tag: str = "Warfare"  # Défini au niveau de la classe
    
    def __init__(self, cluster_fullname: str):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit = MissionToolkit()
        self.cluster_fullname = cluster_fullname
        self.model = get_model_for_agent(self.name)
        self.model_with_tools = self.model.bind_tools(self.toolkit.get_tools())
        self.llm = self.model_with_tools
        self.agent_settings = get_agent_settings(self.name)
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["mission"]
        
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
            toolkit=self.toolkit
        )
        
    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Mission expert.
        
        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
            "You are a operationnal expert with access to tools for retrieving and analyzing military mission data "
            "from the information provided CSV file.\n\n"
            "### Your Primary Responsibilities:\n"
            "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
            "   - Ship activity.\n"
            "   - Communication protocol used.\n"
            "   - Ship name and missions\n"
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