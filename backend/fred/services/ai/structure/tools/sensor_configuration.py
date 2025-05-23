# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from services.sensor.sensor_structures import SensorConfigurationSeries

class SensorConfigurationInput(BaseModel):
    """
    Input schema for retrieving sensor configuration.

    Attributes:
        neighbourhood_id (str): Naval neighbourhood id.
    """
    neighbourhood_id: str = Field(description="Frequency in MHz")

def get_sensor_configurations(
        neighbourhood_id: str
) -> SensorConfigurationSeries:
    """
    Retrieves the sensor configurations from the specified service.

    Args:
        neighbourhood_id (str): Naval neighbourhood id.

    Returns:
        SensorConfigurationSeries: The object containing sensor configurations data.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/sensor_configurations"
    response = requests.get(
        url,
        params={
            "neighbourhood_id": neighbourhood_id,
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()

get_sensor_configurations_tool = StructuredTool.from_function(
    func=get_sensor_configurations,
    name="get_sensor_configurations",
    description=(
        "Retrieve the sensor configurations to all the military active ships located near a specific maritime neighbourhood."
    ),
    args_schema=SensorConfigurationInput,
    return_direct=True,
)