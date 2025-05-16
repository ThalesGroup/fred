import requests
from langchain_core.tools import StructuredTool
from services.theorical_radio.theorical_radio_structures import TheoricalRadioSeries

def get_radio_data() -> TheoricalRadioSeries:
    """
    Retrieves the information on theorical radio data.

    Returns:
        TheoricalRadioSeries: The object containing theorical radio data.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/theorical_radio"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_radio_data_tool = StructuredTool.from_function(
    func=get_radio_data,
    name="get_radio_data",
    description=(
        "Retrieves informations ontheorical radio data."
    ),
    return_direct=True,
)