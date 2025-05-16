from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from services.ai.structure.tools.theater_analysis import get_ship_identification_tool
from services.ai.structure.tools.theater_analysis_sensor_data import get_sensor_data_tool
from services.ai.structure.tools.theater_analysis_get_active_ships import get_active_ships_tool
from services.ai.structure.tools.mission import get_mission_tool

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
