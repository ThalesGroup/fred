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

from fred.application_context import get_app_context, get_configuration
from fred.services.sensor.sensor_abstract_service import AbstractSensorService, AbstractSensorConfigurationService
from fred.services.sensor.sensor_csv_service import SensorCsvService, SensorConfigurationCsvService
from fred.common.structure import DatabaseTypeEnum


class SensorService:
    def __new__(cls) -> AbstractSensorService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return SensorCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")
            

class SensorConfigurationService:
    def __new__(cls) -> AbstractSensorConfigurationService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return SensorConfigurationCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type}")