#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
"""
Services to extract and transform the power kepler metrics data
"""
import csv
import logging
import os
import pathlib
import sys
from datetime import datetime

from fred.application_context import get_configuration
from services.cluster_consumption.cluster_consumption_abstract_service import AbstractClusterConsumptionService
from services.cluster_consumption.cluster_consumption_structures import ClusterConsumptionSeries, DetailSeries
from common.structure import PrecisionEnum, Configuration, Series
from common.utils import sample_data, SampleDataType
from services.frontend.frontend_structures import Observation
logger = logging.getLogger(__name__)

class ClusterConsumptionCsvService(AbstractClusterConsumptionService):
    """
    A simulated cluster consumption service. It provides data for testing purposes in response to cluster level requests.
    The data comes from two CSV files. One for the Wh data and one for the GCo2 data.
    """

    def __init__(self):
        configuration = get_configuration()
        if hasattr(sys.modules['__main__'], '__file__'):
            main_path_dir = pathlib.Path(os.path.abspath(sys.modules['__main__'].__file__)).parent
        else:
            raise RuntimeError("This code must be run as part of a main script with a file path.")

        self.wh_data_file = main_path_dir / configuration.database.csv_files.energy_footprint
        self.gco2_data_file = main_path_dir / configuration.database.csv_files.carbon_footprint
        self.energy_mix_data_file = main_path_dir / configuration.database.csv_files.energy_mix
        self.finops_data_file = main_path_dir / configuration.database.csv_files.financial_footprint

    def consumption_finops(self, start: datetime, end: datetime, cluster: str, precision: PrecisionEnum) -> Series:
        """
        Generate a CSV file with simulated FinOps data based on Wh and GCo2 consumption values.

        Args:
            start (datetime): Start date for data generation.
            end (datetime): End date for data generation.
            cluster (str): Cluster identifier.
            precision (PrecisionEnum): Precision level for data sampling.
        """
        factor = 1.0 if "aws" in cluster or "rift" in cluster else 0.23
        result = self._process_csv(self.finops_data_file, start, end, precision, SampleDataType.SUM, "USD")
        result.values = [value * factor for value in result.values]
        for detail in result.details:
            detail.values = [value * factor for value in detail.values]
        result.auc = result.auc * factor
        return result

    def compute_observation(self, start: datetime, end: datetime,
                            cluster: str, precision: PrecisionEnum, unit_type: str) -> Observation:
        """
        Compute a single Observation based on aggregated consumption data.
        """
        consumption_series = self.consumption_wh(start, end, cluster, precision) if unit_type == "wh" else \
            self.consumption_gco2(start, end, cluster, precision) if unit_type == "gco2" else \
                self.consumption_mix(start, end, precision)

        total_value = sum(detail.values for detail in consumption_series.details)
        return Observation(value=total_value, unit=consumption_series.unit)

    def consumption_gco2(self, start: datetime, end: datetime, cluster: str,
                         precision: PrecisionEnum) -> ClusterConsumptionSeries:
        """
        Process the GCO2 data from the CSV file and return the ClusterConsumptionSeries.
        """
        factor = 1.0 if "aws" in cluster or "rift" in cluster else 0.17
        result = self._process_csv(self.gco2_data_file, start, end, precision, SampleDataType.SUM, "gco2")
        result.values = [value * factor for value in result.values]
        for detail in result.details:
            detail.values = [value * factor for value in detail.values]
        result.auc = result.auc * factor
        return result

    def consumption_wh(self, start: datetime, end: datetime, cluster: str,
                       precision: PrecisionEnum) -> ClusterConsumptionSeries:
        """
        Process the Wh data from the CSV file and return the ClusterConsumptionSeries.
        """
        factor = 1.0 if "aws" in cluster or "rift" in cluster else 0.21
        result = self._process_csv(self.wh_data_file, start, end, precision, SampleDataType.SUM, "wh")
        result.values = [value * factor for value in result.values]
        for detail in result.details:
            detail.values = [value * factor for value in detail.values]
        result.auc = result.auc * factor
        return result

    def consumption_mix(self, start: datetime, end: datetime, precision: PrecisionEnum) -> ClusterConsumptionSeries:
        """
        Process the energy mix data from the CSV file and return the ClusterConsumptionSeries.
        """
        return self._process_csv(self.energy_mix_data_file, start, end, precision, SampleDataType.AVERAGE, "mix")

    @staticmethod
    def _process_csv(file_path: pathlib.Path, start: datetime, end: datetime,
                     precision: PrecisionEnum, method: SampleDataType, unit: str) -> ClusterConsumptionSeries:
        """
        Helper method to process the CSV file and return ClusterConsumptionSeries.
        """
        total_values = []
        original_timestamps = []
        numeric_columns = set()

        with open(file_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            headers = reader.fieldnames
            details = {name: [] for name in headers if name != 'timestamp'}

            for row in reader:
                try:
                    ts = datetime.fromisoformat(row['timestamp']).replace(tzinfo=None)
                except ValueError:
                    logger.debug(f"Skipping invalid timestamp: {row['timestamp']}")
                    continue
                start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)
                total_is_present = False

                if start <= ts <= end:
                    original_timestamps.append(ts)
                    row_detail_values = {}

                    for key in headers:
                        if key == 'timestamp':
                            continue
                        if key == 'total':
                            try:
                                total_values.append(float(row[key]))
                                total_is_present = True
                            except ValueError:
                                pass
                            continue
                        value = row[key]
                        try:
                            float_value = float(value)
                            row_detail_values[key] = float_value
                            numeric_columns.add(key)
                        except ValueError:
                            details.pop(key, None)

                    if row_detail_values:
                        acc = 0
                        for key, value in row_detail_values.items():
                            details[key].append(value)
                            acc += value
                        if not total_is_present:  # There was not an explicit "total" column
                            total_values.append(acc)

        downsampled_timestamps, downsampled_total_values = sample_data(
            original_timestamps, total_values, precision, method
        )

        downsampled_details = {
            key: sample_data(original_timestamps, details[key], precision, method)[1]
            for key in numeric_columns
        }

        detail_series = [
            DetailSeries(name=name, kind="namespace", values=downsampled_details[name])
            for name in numeric_columns
        ]

        return ClusterConsumptionSeries(
            timestamps=downsampled_timestamps,
            values=downsampled_total_values,
            auc=sum(downsampled_total_values),
            details=detail_series,
            unit=unit  # use 'wh' or 'gco2' based on the method
        )
