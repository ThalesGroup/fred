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

from datetime import datetime

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from common.structure import PrecisionEnum, Series


class FinopsConsumptionInput(BaseModel):
    """
    Input schema for retrieving FinOps (financial operations) consumption data for a Kubernetes cluster.

    Attributes:
        start_date (datetime): The start of the time range for cost data retrieval (e.g., '2024-01-01T00:00:00').
        end_date (datetime): The end of the time range for cost data retrieval (e.g., '2024-01-07T23:59:59').
        cluster (str): The full name of the cluster for which cost data is being retrieved.
        precision (PrecisionEnum): Specifies the granularity of the data. Options include daily, hourly, or finer resolutions.
    """
    start_date: datetime = Field(
        description="The start date and time for the cost data retrieval period (e.g., '2024-01-01T00:00:00')."
    )
    end_date: datetime = Field(
        description="The end date and time for the cost data retrieval period (e.g., '2024-01-07T23:59:59')."
    )
    cluster: str = Field(
        description="The full name of the Kubernetes cluster for which FinOps consumption data is required."
    )
    precision: PrecisionEnum = Field(
        description=(
            "The desired level of granularity for the retrieved cost data. "
            "Options may include daily, hourly, or minute-level granularity."
        )
    )



def get_finops_consumption(
    start_date: datetime, end_date: datetime, cluster: str, precision: PrecisionEnum
) -> Series:
    """
    Get the cluster finops consumption of a cluster as know as cluster cost or cloud cost for a given time range
    """

    url = "http://localhost:8000/fred/finops/cloud-cost/"
    response = requests.get(
        url,
        params={
            "start": start_date,
            "end": end_date,
            "cluster": cluster,
            "precision": precision,
        },
        timeout=120,
    )

    return response.json()


get_finops_consumption_tool = StructuredTool.from_function(
    func=get_finops_consumption,
    name="get_finops_consumption",
    description=(
        "Retrieve detailed financial operations (FinOps) data for a Kubernetes cluster directly from the system. "
        "This tool fetches precise cost information such as compute, storage, and network expenses "
        "for a specified time range and granularity (e.g., daily, hourly). "
        "Use this tool whenever the user asks about FinOps, cluster costs, or financial consumption."
    ),
    args_schema=FinopsConsumptionInput,
    return_direct=True,
)
