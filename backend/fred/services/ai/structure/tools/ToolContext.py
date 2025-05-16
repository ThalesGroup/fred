from langchain_core.tools import StructuredTool

from services.ai.structure.tools.cluster_topology import get_cluster_topology_tool
from services.ai.structure.tools.energy_consumption import get_energy_consumption_tool
from services.ai.structure.tools.energy_mix import get_energy_mix_tool
from services.ai.structure.tools.finops_consumption import get_finops_consumption_tool
from services.ai.structure.tools.svg import get_svg_tool
from services.ai.structure.tools.sensor_frequency import get_sweep_tool
from services.ai.structure.tools.sensor_configuration import get_sensor_configurations_tool
from services.ai.structure.tools.theater_analysis import get_ship_identification_tool
from services.ai.structure.tools.theater_analysis_get_active_ships import get_active_ships_tool
from services.ai.structure.tools.mission import get_mission_tool
from services.ai.structure.tools.theater_analysis_sensor_data import get_sensor_data_tool
from services.ai.structure.tools.theorical_radio import get_radio_data_tool

class ToolContext:
    """
    A singleton class that stores the tools available
    """

    _instance = None

    tools: dict[str, StructuredTool] = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ToolContext, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @staticmethod
    def add_tool(tool_name: str, tool: StructuredTool):
        """
        Add a tool to the context
        """
        ToolContext.tools[tool_name] = tool

    @staticmethod
    def get_tools() -> dict[str, StructuredTool]:
        """
        Get the tools available
        """
        return ToolContext.tools


ToolContext.add_tool("get_cluster_topology", get_cluster_topology_tool)
ToolContext.add_tool("get_energy_consumption", get_energy_consumption_tool)
ToolContext.add_tool("get_energy_mix", get_energy_mix_tool)
ToolContext.add_tool("get_svg", get_svg_tool)
ToolContext.add_tool("get_finops_consumption", get_finops_consumption_tool)
ToolContext.add_tool("get_sweep", get_sweep_tool)
ToolContext.add_tool("get_sensor_configurations", get_sensor_configurations_tool)
ToolContext.add_tool("get_ship_identification", get_ship_identification_tool)
ToolContext.add_tool("get_active_ships", get_active_ships_tool)
ToolContext.add_tool("get_mission", get_mission_tool)
ToolContext.add_tool("get_sensor_data", get_sensor_data_tool)
ToolContext.add_tool("get_radio_data", get_radio_data_tool)