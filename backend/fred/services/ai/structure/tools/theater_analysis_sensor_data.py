import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from services.theater_analysis.theater_analysis_structures import DetectedDataSeries

def get_sensor_data() -> DetectedDataSeries:
    """
    Retrieves the logged signal data detected.

    Returns:
        DetectedDataSeries: The object containing data detected by the sensor on ships offshore.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/sensor_data"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_sensor_data_tool = StructuredTool.from_function(
    func=get_sensor_data,
    name="get_sensor_data",
    description=(
        "Retrieves informations on data captured by the sensor."
    ),
    return_direct=True,
)