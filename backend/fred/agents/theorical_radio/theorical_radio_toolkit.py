from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

from services.ai.structure.tools.theorical_radio import get_radio_data_tool

class TheoricalRadioToolkit(BaseToolkit):
    """
    Toolkit for theorical radio data tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = [
            get_radio_data_tool
        ]

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools