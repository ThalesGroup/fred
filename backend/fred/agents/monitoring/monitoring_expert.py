from datetime import datetime

from flow import AgentFlow
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agents.monitoring.monitoring_toolkit import MonitoringToolkit
from fred.application_context import get_agent_settings, get_model_for_agent

class MonitoringExpert(AgentFlow):
    """
    Expert to provide guidance on Kubernetes monitoring.
    """
    # Class-level attributes for metadata
    name: str = "MonitoringExpert"
    role: str = "Monitoring Expert"
    nickname: str = "Maya"
    description: str = (
                "A Kubernetes monitoring expert that retrieves raw data and performs aggregation "
                "to provide insights on cluster performance, resource consumption, energy usage, "
                "energy mix and financial costs. This expert retrieves raw data in JSON format, processes it, "
                "and generates meaningful aggregated results for the user."
            )
    icon: str = "monitoring_agent"
    categories: list[str] = []
    tag: str = "Frugal IT"  # Défini au niveau de la classe
    
    def __init__(self, 
                 cluster_fullname: str
                 ):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.toolkit = MonitoringToolkit()
        self.cluster_fullname = cluster_fullname
        self.model = get_model_for_agent(self.name)
        self.model_with_tools = self.model.bind_tools(self.toolkit.get_tools())
        self.llm = self.model_with_tools
        self.agent_settings = get_agent_settings(self.name)
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["Monitoring"]
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
        Generates the base prompt for the Kubernetes expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
                "You are a Kubernetes monitoring expert with access to tools for retrieving and analyzing data "
                f"from the cluster you manage. Your cluster is named {self.cluster_fullname}.\n\n"
                "### Your Primary Responsibilities:\n"
                "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
                "   - Energy consumption (grouped by namespace).\n"
                "   - Energy mix for the region where the cluster resides.\n"
                "   - Financial costs (e.g., compute, storage, and network expenses).\n"
                "2. **Aggregate Data**: Process the raw data you retrieve by:\n"
                "   - Calculating totals, averages, and trends.\n"
                "   - Summarizing key insights in a user-friendly manner.\n\n"
                "### Key Instructions:\n"
                "1. Always use tools to fetch data before providing answers. Avoid generating generic guidance or assumptions.\n"
                "2. Aggregate and analyze the data to directly answer the user's query.\n"
                "3. Present the results clearly, with summaries, breakdowns, and trends where applicable.\n\n"
                f"The current date is {self.current_date}.\n\n"
                "### Example Queries and Outputs:\n"
                "- Query: 'What was the energy consumption for the cluster last week?'\n"
                "  - Fetch the raw data using the energy consumption tool.\n"
                "  - Aggregate by namespace and calculate the weekly total and daily average.\n"
                "  - Present results in this format: \n"
                "    ```json\n"
                "    {\n"
                "        'total_energy_consumption': '500 kWh',\n"
                "        'daily_average': '71.43 kWh',\n"
                "        'namespace_breakdown': {\n"
                "            'namespace1': '200 kWh',\n"
                "            'namespace2': '300 kWh'\n"
                "        }\n"
                "    }\n"
                "    ```\n"
                "- Query: 'How much did the cluster cost last week?'\n"
                "  - Use the financial consumption tool to get raw cost data.\n"
                "  - Calculate the weekly total and average daily cost.\n"
                "  - Include a breakdown by components (e.g., compute, storage, network).\n"
                "  - Present results in a structured and concise format."
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