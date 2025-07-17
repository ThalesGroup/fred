# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from common.structure import PrecisionEnum
from common.structure import SampleDataType
from common.utils import sample_data, auc_calculation
from services.cluster_consumption.cluster_consumption_structures import ClusterConsumptionSeries, \
    ClusterConsumption, DetailSeries, \
    Detail


# Parse ClusterConsumption data to ClusterConsumptionSeries
def parse_to_cluster_consumption_series(cluster_consumptions: list[ClusterConsumption]) -> ClusterConsumptionSeries:
    """
    Parse the consumption data to the series format
    """
    res = ClusterConsumptionSeries(
        timestamps=[],
        values=[],
        auc=0,
        details=[],
        unit=""
    )

    # Extract the main serie of consumption
    for cluster_consumption in cluster_consumptions:
        res.timestamps.append(cluster_consumption.timestamp)
        res.values.append(cluster_consumption.value)
        # Add the global timestamp to all details
        for detail in cluster_consumption.details:
            detail.timestamp = cluster_consumption.timestamp

    res.unit = cluster_consumptions[0].unit if len(cluster_consumptions) > 0 else ""
    res.auc = auc_calculation(res.values)

    # Extract details and group them by name and kind and add timestamps
    global_details: list[Detail] = []
    for cluster_consumption in cluster_consumptions:
        for detail in cluster_consumption.details:
            global_details.append(detail)

    # Sort the details by name and kind
    global_details = sorted(global_details, key=lambda x: (x.name, x.kind))
    for name, kind in set((detail.name, detail.kind) for detail in global_details):
        timestamps = []
        values = []
        for detail in global_details:
            if detail.name == name and detail.kind == kind:
                timestamps.append(detail.timestamp)
                values.append(detail.value)
        res.details.append(DetailSeries(
            name=name,
            kind=kind,
            values=values,
        ))

    return res


# Aggregation of consumption data by steps in minutes
def resample_cluster_consumption(cluster_consumption_series: ClusterConsumptionSeries,
                                 precision: PrecisionEnum) -> ClusterConsumptionSeries:
    """
    Aggregate the consumption data by the given precision
    """
    resampled_timestamps, resampled_values = sample_data(cluster_consumption_series.timestamps,
                                                         cluster_consumption_series.values,
                                                         precision, SampleDataType.SUM)

    for detail in cluster_consumption_series.details:
        _, detail.values = sample_data(cluster_consumption_series.timestamps, detail.values, precision,
                                       SampleDataType.SUM)

    return ClusterConsumptionSeries(
        timestamps=resampled_timestamps,
        values=resampled_values,
        auc=auc_calculation(resampled_values),
        details=cluster_consumption_series.details,
        unit=cluster_consumption_series.unit
    )


def compute_cost_from_footprint(energy_wh, carbon_gco2):
    """
    Compute the total cost from energy (Wh) and carbon (gCO2) values.

    Args:
        energy_wh (float): The energy consumption in Wh.
        carbon_gco2 (float): The carbon consumption in gCO2.

    Returns:
        float: The total computed cost in USD.
    """
    cost_per_kwh = 0.42  # USD per kWh
    cost_per_ton_co2 = 150  # USD per ton of CO2

    # Compute the cost based on energy consumption (Wh to kWh)
    cost_from_energy = (energy_wh / 1000) * cost_per_kwh

    # Compute the cost based on carbon consumption (gCO2 to tons)
    cost_from_carbon = (carbon_gco2 / 1000) * cost_per_ton_co2

    # Average the two costs to calculate the total cost
    total_cost = (cost_from_energy + cost_from_carbon) / 1.3

    return total_cost
