import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from services.theater_analysis.theater_analysis_structures import TheaterAnalysisSeries

def get_ship_identification() -> TheaterAnalysisSeries:
    """
    Retrieves the ship location information from the specified protocol.

    Args:
        protocol (str): Radio protocol used by the ship.

    Returns:
        TheaterAnalysisSeries: The object containing ship location information.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/ship_identification"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_ship_identification_tool = StructuredTool.from_function(
    func=get_ship_identification,
    name="get_ship_identification",
    description=(
        "Retrieve the ship location that emit a signal from a radio sending data with a protocol identified as abnormal."
    ),
    return_direct=True,
)