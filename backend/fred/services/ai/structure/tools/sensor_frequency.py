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
from services.sensor.sensor_structures import SensorSeries

def get_sweep() -> SensorSeries:
    """
    Retrieves frequency analysis data from the specified service.

    Returns:
        SensorSeries: The object containing frequency analysis data.
    """
    
    url = "http://localhost:8000/fred/guerre_elec/sweep"
    response = requests.get(
        url,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()
    # return SensorSeries.model_validate_json(response.json())

get_sweep_tool = StructuredTool.from_function(
    func=get_sweep,
    name="get_sweep",
    description=(
        "Retrieve frequency analysis data based on specified parameters."
    ),
    return_direct=True,
)