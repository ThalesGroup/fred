from datetime import datetime

from flow import AgentFlow
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agents.monitoring.monitoring_toolkit import MonitoringToolkit
from fred.application_context import get_agent_settings, get_model_for_agent

class K8SOperatorExpert(AgentFlow):
    """
    Expert to execute actions on a Kubernetes cluster.
    """
    # Class-level attributes for metadata
    name: str = "K8SOperatorExpert"
    role: str = "Kubernetes Operator Expert"
    nickname: str = "Kimberley"
    description: str = (
                "A Kubernetes monitoring & operator expert that can perform various actions on a kubernetes cluster "
                "to provide insights on cluster performance, state of the current installed resources, "
                "pod status, container information, logs and many more. This expert performs the relevant "
                "kubectl and helm commands in order to fulfill its mission and generates meaningful "
                "and aggregated results for the user."
            )
    icon: str = "k8s_operator_agent"
    categories: list[str] = []
    tag: str = "k8s operator"  # Défini au niveau de la classe
    
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
            toolkit=self.toolkit 
        )
        

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Kubernetes expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """

        return (
                "You are a Kubernetes monitoring & operator expert with access to tools for retrieving and analyzing data "
                f"from the cluster you manage. Your cluster is named {self.cluster_fullname}.\n\n"
                "### Your Primary Responsibilities:\n"
                "1. **Retrieve Data**: Use the provided tools to fetch data for:\n"
                "   - Pods & containers statuses and logs .\n"
                "   - The state of the deployed resources and wether they are functionning properly.\n"
                "   - Retrieve any malfuction in the cluster.\n"
                "2. **Aggregate Data**: Execute appropriate commands using the kubernetes MCP server in order to:\n"
                "   - Get and interpret the logs and the resource statuses.\n"
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