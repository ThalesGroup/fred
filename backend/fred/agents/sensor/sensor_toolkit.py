from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from services.ai.structure.tools.sensor_frequency import get_sweep_tool
from services.ai.structure.tools.sensor_configuration import get_sensor_configurations_tool

class SensorToolkit(BaseToolkit):
    """
    Toolkit for sensor tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = [
            get_sweep_tool,
            # get_sensor_configurations_tool
        ]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
