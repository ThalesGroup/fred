from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from services.ai.structure.tools.energy_consumption import get_energy_consumption_tool
from services.ai.structure.tools.energy_mix import get_energy_mix_tool
from services.ai.structure.tools.finops_consumption import get_finops_consumption_tool


class MonitoringToolkit(BaseToolkit):
    """
    Toolkit for monitoring tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = [
            get_energy_consumption_tool,
            get_energy_mix_tool,
            get_finops_consumption_tool,
        ]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
