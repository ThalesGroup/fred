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

from app.monitoring.tool_monitoring.monitor_tool import monitor_tool
from app.services.ai.structure.tools.energy_consumption import get_energy_consumption_tool
from app.services.ai.structure.tools.energy_mix import get_energy_mix_tool
from app.services.ai.structure.tools.finops_consumption import get_finops_consumption_tool


class MonitoringToolkit(BaseToolkit):
    """
    Toolkit for monitoring tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        raw_tools = [
            get_energy_consumption_tool,
            get_energy_mix_tool,
            get_finops_consumption_tool,
        ]
        self.tools = [monitor_tool(tool) for tool in raw_tools]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
