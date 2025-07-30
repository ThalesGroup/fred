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

from app.features.frugal.cluster_consumption.cluster_consumption_structures import (
    ClusterConsumption,
)
from app.common.structures import PrecisionEnum


class EnergyMixInput(BaseModel):
    """
    Input schema for retrieving the energy mix (electricity mix or power mix) over a specific date range.

    Attributes:
        start_date (str): The start date for the energy mix data retrieval (e.g., '2024-01-01').
        end_date (str): The end date for the energy mix data retrieval (e.g., '2024-01-07').
        precision (PrecisionEnum): Specifies the granularity of the data, such as daily or hourly breakdown.
    """

    start_date: str = Field(
        description="Start date for the energy mix data retrieval in 'YYYY-MM-DD' format. Example: '2024-01-01'."
    )
    end_date: str = Field(
        description="End date for the energy mix data retrieval in 'YYYY-MM-DD' format. Example: '2024-01-07'."
    )
    precision: PrecisionEnum = Field(
        description=(
            "The granularity of the energy mix data. Options may include 'daily', 'hourly', "
            "or 'minute-level' precision, depending on the available data."
        )
    )


def get_energy_mix(
    start_date: str, end_date: str, precision: PrecisionEnum
) -> ClusterConsumption:
    """
    Get the energy-mix also known as the electricity mix or power mix measurement for a given date range
    """

    url = "http://localhost:8000/fred/energy/mix/"
    response = requests.get(
        url,
        params={"start": start_date, "end": end_date, "precision": precision},
        timeout=120,
    )

    return response.json()


get_energy_mix_tool = StructuredTool.from_function(
    func=get_energy_mix,
    name="get_energy_mix",
    description=(
        "Retrieve the energy mix (electricity mix or power mix) for a specific time range. "
        "The energy mix provides the breakdown of energy sources (e.g., solar, wind, grid) "
        "used in the region where the cluster operates. Specify the start and end dates, "
        "and optionally the desired level of precision (e.g., daily, hourly)."
        "Use this tool whenever the user asks about electricity mix, power mix or the carbon footprint of the energy."
    ),
    args_schema=EnergyMixInput,
    return_direct=True,
)
