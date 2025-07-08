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