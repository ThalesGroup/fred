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

from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from fred.agents.keda.keda_tools import (generate_keda_cron_configuration,
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
