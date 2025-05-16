from typing import override, List

from langchain_core.tools import BaseToolkit, BaseTool
from pydantic import Field

class K8SOperatorToolkit(BaseToolkit):
    """
    Toolkit for K8S monitoring and operator tools
    """

    tools: List[BaseTool] = Field(default_factory=list, description="List of the tools.")

    def __init__(self):
        super().__init__()
        self.tools = []

    @override
    def get_tools(self) -> list[BaseTool]:
        """Get the tools in the toolkit."""
        return self.tools
