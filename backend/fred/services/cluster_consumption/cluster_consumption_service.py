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
from fred.services.cluster_consumption.cluster_consumption_abstract_service import AbstractClusterConsumptionService
from fred.services.cluster_consumption.cluster_consumption_csv_service import ClusterConsumptionCsvService
from fred.common.structure import Configuration, DatabaseTypeEnum


class ClusterConsumptionService:
    def __new__(cls) -> AbstractClusterConsumptionService:
        match get_configuration().database.type:
            case DatabaseTypeEnum.csv:
                return ClusterConsumptionCsvService()
            case _:
                raise NotImplementedError(f"Database type {get_configuration().database.type} is not supported.")
