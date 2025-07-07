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

from fred.services.ai.structure.tools.theater_analysis import get_ship_identification_tool
from fred.services.ai.structure.tools.theater_analysis_sensor_data import get_sensor_data_tool
from fred.services.ai.structure.tools.theater_analysis_get_active_ships import get_active_ships_tool
from fred.services.ai.structure.tools.mission import get_mission_tool

class TheaterAnalysisToolkit(BaseToolkit):
    """
    Toolkit for theater_analysis tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = [
            get_ship_identification_tool,
            get_sensor_data_tool,
            get_mission_tool,
            get_active_ships_tool
        ]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
