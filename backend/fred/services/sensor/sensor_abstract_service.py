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

from fred.services.sensor.sensor_structures import SensorSeries, SensorConfigurationSeries

class AbstractSensorService(ABC):
    """
    Interface to retrieve frequency metrics.
    One implementations is provided that uses real data
    stored in some file backends.
    """

    @abstractmethod
    def sweep(self) -> SensorSeries:
        """
        Perform a frequency sweep.
        
        Returns:
            SensorSeries: The frequency sweep series.
        """
        ...
        

class AbstractSensorConfigurationService(ABC):
    """
    Interface to retrieve sensor configurations.
    One implementation is provided that uses real data
    stored in some file backend.
    """

    @abstractmethod
    def get_sensor_configurations(self, neighbourhood_id: str) \
            -> SensorConfigurationSeries:
        """
        Get the list of sensor configurations for all the ships located in the
        provided neighbourhood_id.
        
        Args:
            neighbourhood_id (str): Naval neighbourhood id.

        Returns:
            SensorConfigurationSeries: The object containing sensor configurations data.
        """
        ...