import requests
from langchain_core.tools import StructuredTool
from services.mission.mission_structures import MissionSeries

def get_mission() -> MissionSeries:
    """
    Retrieves the mission information.

    Returns:
        MissionSeries: The object containing data on the missions.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/mission"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_mission_tool = StructuredTool.from_function(
    func=get_mission,
    name="get_mission",
    description=(
        "Retrieves informations on the mission, which boat emits, which ones are active or not."
    ),
    return_direct=True,
)