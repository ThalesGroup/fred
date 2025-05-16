import requests
from langchain_core.tools import StructuredTool
from services.theater_analysis.theater_analysis_structures import TheaterAnalysisSeries

def get_active_ships() -> TheaterAnalysisSeries:
    """
    Retrieves data related to active ships detected.

    Returns:
        TheaterAnalysisSeries: The object containing active ships information.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/active_ships"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_active_ships_tool = StructuredTool.from_function(
    func=get_active_ships,
    name="get_active_ships",
    description=(
        "Retrieves informations on detected ships."
    ),
    return_direct=True,
)