from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from agents.keda.keda_tools import (generate_keda_cron_configuration,
                                                      generate_keda_prometheus_configuration, get_prometheus_url_tool,
                                                      get_workload_tool, get_workload_name_list_tool)


class KedaToolkit(BaseToolkit):
    """
    Toolkit for KEDA tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools


class KedaToolkitBuilder:
    def __init__(self, kube_service):
        self.kube_service = kube_service

    def build(self):
        tools = [
            generate_keda_cron_configuration,
            generate_keda_prometheus_configuration,
            get_prometheus_url_tool(self.kube_service),
            get_workload_tool(self.kube_service),
            get_workload_name_list_tool(self.kube_service),
        ]
        return KedaToolkit(tools=tools)
