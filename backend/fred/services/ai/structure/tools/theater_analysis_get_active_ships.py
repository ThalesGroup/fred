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