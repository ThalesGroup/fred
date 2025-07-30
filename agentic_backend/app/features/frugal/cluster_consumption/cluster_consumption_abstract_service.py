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

from abc import ABC, abstractmethod
from datetime import datetime

from app.common.structures import PrecisionEnum, CompareResult, Series
from app.common.utils import compare_two_windows
from app.features.frugal.cluster_consumption.cluster_consumption_structures import ClusterConsumptionSeries


class AbstractClusterConsumptionService(ABC):
    """
    Interface to retrieve energy or carbon footprint metrics.
    Two implementations are provided. One uses simulated data and the other uses real data
    stored in some file or elasticsearch backends.
    """

    @abstractmethod
    def consumption_gco2(self, start: datetime, end: datetime, cluster: str, precision: PrecisionEnum) \
            -> ClusterConsumptionSeries:
        """
        Get the gCO2 metrics consumption for a given time range.

        Args:
            start (datetime): The start of the time range.
            end (datetime): The end of the time range.
            cluster (str): The cluster of the metrics.
            precision (PrecisionEnum): The precision of the metrics.

        Returns:
            ClusterConsumptionSeries: The gCO2 metrics consumption series.
        """
        ...

    @abstractmethod
    def consumption_wh(self, start: datetime, end: datetime, cluster: str, precision: PrecisionEnum) \
            -> ClusterConsumptionSeries:
        """
        Get the Wh metrics consumption for a given time range.

        Args:
            start (datetime): The start of the time range.
            end (datetime): The end of the time range.
            cluster (str): The cluster of the metrics.
            precision (PrecisionEnum): The precision of the metrics.

        Returns:
            ClusterConsumptionSeries: The Wh metrics consumption series.
        """
        ...

    @abstractmethod
    def consumption_finops(self, start: datetime, end: datetime, cluster: str, precision: PrecisionEnum) -> Series:
        """
        Get the finops metrics for a given time range.

        Args:
            start (datetime): The start of the time range.
            end (datetime): The end of the time range.
            cluster (str): The cluster of the metrics.
            precision (PrecisionEnum): The precision of the metrics.

        Returns:
            Series: The finops metrics' series.
        """
        ...

    @abstractmethod
    def consumption_mix(self, start: datetime, end: datetime, precision: PrecisionEnum) -> ClusterConsumptionSeries:
        """
        Get the energy mix consumption for a given time range.

        Args:
            start (datetime): The start of the time range.
            end (datetime): The end of the time range.
            precision (PrecisionEnum): The precision of the metrics.

        Returns:
            ClusterConsumptionSeries: The energy mix consumption series.
        """
        ...

    def consumption_gco2_compare(self,
                                 start_window_1: datetime, end_window_1: datetime,
                                 start_window_2: datetime, end_window_2: datetime,
                                 cluster: str) -> CompareResult:
        """
        Compare two windows of gCO2 metrics consumption for a given cluster and time ranges.

        Args:
            start_window_1 (datetime): The start of the first window.
            end_window_1 (datetime): The end of the first window.
            start_window_2 (datetime): The start of the second window.
            end_window_2 (datetime): The end of the second window.
            cluster (str): The cluster of the metrics.

        Returns:
            CompareResult: The comparison result of the two windows.
        """
        return compare_two_windows(
            self.consumption_gco2(start_window_1, end_window_1, cluster, PrecisionEnum.NONE),
            self.consumption_gco2(start_window_2, end_window_2, cluster, PrecisionEnum.NONE),
            start_window_1, end_window_1, start_window_2, end_window_2, cluster
        )

    def consumption_wh_compare(self,
                               start_window_1: datetime, end_window_1: datetime,
                               start_window_2: datetime, end_window_2: datetime,
                               cluster: str) -> CompareResult:
        """
        Compare two windows of energy metrics consumption for a given cluster and time ranges.

        Args:
            start_window_1 (datetime): The start of the first window.
            end_window_1 (datetime): The end of the first window.
            start_window_2 (datetime): The start of the second window.
            end_window_2 (datetime): The end of the second window.
            cluster (str): The cluster of the metrics.

        Returns:
            CompareResult: The comparison result of the two windows.
        """
        return compare_two_windows(
            self.consumption_wh(start_window_1, end_window_1, cluster, PrecisionEnum.NONE),
            self.consumption_wh(start_window_2, end_window_2, cluster, PrecisionEnum.NONE),
            start_window_1, end_window_1, start_window_2, end_window_2, cluster
        )

    def consumption_finops_compare(self,
                                   start_window_1: datetime, end_window_1: datetime,
                                   start_window_2: datetime, end_window_2: datetime,
                                   cluster: str) -> CompareResult:
        """
        Compare two windows of finops metrics for a given cluster and time ranges.

        Args:
            start_window_1 (datetime): The start of the first window.
            end_window_1 (datetime): The end of the first window.
            start_window_2 (datetime): The start of the second window.
            end_window_2 (datetime): The end of the second window.
            cluster (str): The cluster of the metrics.

        Returns:
            CompareResult: The comparison result of the two windows.
        """
        return compare_two_windows(
            self.consumption_finops(start_window_1, end_window_1, cluster, PrecisionEnum.NONE),
            self.consumption_finops(start_window_2, end_window_2, cluster, PrecisionEnum.NONE),
            start_window_1, end_window_1, start_window_2, end_window_2, cluster
        )
