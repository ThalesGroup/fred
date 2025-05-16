from datetime import datetime

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from services.cluster_consumption.cluster_consumption_structures import (
    ClusterConsumption,
)
from common.structure import PrecisionEnum


class EnergyConsumptionInput(BaseModel):
    """
    Input schema for retrieving energy consumption data of a Kubernetes cluster.

    Attributes:
        start_date (datetime): The start of the time range for energy data retrieval.
        end_date (datetime): The end of the time range for energy data retrieval.
        cluster (str): The full name of the cluster to retrieve data for.
        precision (PrecisionEnum): Specifies the precision of the data.
                                   Options may include 'daily', 'hourly', or 'minute-level' granularity.
    """
    start_date: datetime = Field(
        description="Start date and time for the data retrieval period (e.g., '2024-01-01T00:00:00').")
    end_date: datetime = Field(
        description="End date and time for the data retrieval period (e.g., '2024-01-07T23:59:59').")
    cluster: str = Field(description="The full name of the cluster to retrieve energy consumption data for.")
    precision: PrecisionEnum = Field(
        description="The level of granularity for the retrieved data (e.g., daily, hourly).")


def get_energy_consumption(
        start_date: datetime, end_date: datetime, cluster: str, precision: PrecisionEnum
) -> ClusterConsumption:
    """
    Get the cluster energy consumption also known as the eletricity consumption or power consumption for a given time range
    """

    url = "http://localhost:8000/fred/energy/consumption/"
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


get_energy_consumption_tool = StructuredTool.from_function(
    func=get_energy_consumption,
    name="get_energy_consumption",
    description=(
        "Retrieve the energy consumption (electricity or power usage) of a Kubernetes cluster, "
        "grouped by namespace, for a specified time range. Useful for monitoring resource usage, "
        "analyzing energy costs, or understanding environmental impact. "
        "Requires the cluster name, start and end dates, and desired data precision."
        "Use this tool whenever the user asks about energy consumptions, electricity usage, or power usage."
    ),
    args_schema=EnergyConsumptionInput,
    return_direct=True,
)
