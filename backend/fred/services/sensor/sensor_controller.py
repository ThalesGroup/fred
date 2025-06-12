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
Controllers to expose the power kepler metrics endpoints
"""
import traceback
from fastapi import Depends, HTTPException, APIRouter

from security.keycloak import KeycloakUser, get_current_user
from services.sensor.sensor_abstract_service import AbstractSensorService, AbstractSensorConfigurationService
from services.sensor.sensor_service import SensorService, SensorConfigurationService
from services.sensor.sensor_structures import SensorSeries, SensorConfigurationSeries


class SensorController:
    def __init__(self, app: APIRouter):
        service: AbstractSensorService = SensorService()

        fastapi_tags = ["Frequency classification"]

        @app.get("/guerre_elec/sweep",
                 tags=fastapi_tags,
                 description="Get the use of a frequency given the min and max frequency range",
                 summary="Get the use of a frequency given the min and max frequency range"
                 )
        async def get_sweep(user: KeycloakUser = Depends(get_current_user)
                                         ) -> SensorSeries:
            """
            Retrieve frequency usage information for a specified range and type.

            Returns:
                SensorSeries: The usage data for the specified frequency range.
            """
            try:
                return service.sweep()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
            
class SensorConfigurationController:
    def __init__(self, app: APIRouter):
        service: AbstractSensorConfigurationService = SensorConfigurationService()

        fastapi_tags = ["Sensor configuration"]

        @app.get("/guerre_elec/sensor_configurations",
                 tags=fastapi_tags,
                 description="Get the use of a frequency given the min and max frequency range",
                 summary="Get the use of a frequency given the min and max frequency range"
                 )
        async def get_sensor_configurations(neighbourhood_id: str,
                                         user: KeycloakUser = Depends(get_current_user)
                                         ) -> SensorConfigurationSeries:
            """
            Get the list of sensor configurations for all the ships located in the
            provided neighbourhood_id.
            
            Args:
                neighbourhood_id (str): Naval neighbourhood id.

            Returns:
                SensorConfigurationSeries: The object containing sensor configurations data.
            """
            try:
                return service.get_sensor_configurations(neighbourhood_id)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")