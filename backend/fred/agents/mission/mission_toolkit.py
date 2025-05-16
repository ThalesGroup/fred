from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from services.ai.structure.tools.mission import get_mission_tool
class MissionToolkit(BaseToolkit):
    """
    Toolkit for Mission tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = [
            get_mission_tool
        ]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools