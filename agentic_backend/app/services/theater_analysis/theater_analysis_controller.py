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

from fred_core import KeycloakUser, get_current_user
from app.services.theater_analysis.theater_analysis_abstract_service import AbstractTheaterAnalysisService
from app.services.theater_analysis.theater_analysis_service import TheaterAnalysisService
from app.services.theater_analysis.theater_analysis_structures import TheaterAnalysisSeries, DetectedDataSeries

class TheaterAnalysisController:
    def __init__(self, app: APIRouter):
        service: AbstractTheaterAnalysisService = TheaterAnalysisService()

        fastapi_tags = ["Ship Location"]

        @app.get("/guerre_elec/ship_identification",
                 tags=fastapi_tags,
                 description="Get the location of abnormal ships",
                 summary="Get the location of abnormal ships"
                 )
        async def get_theater_analysis(user: KeycloakUser = Depends(get_current_user)
                                         ) -> TheaterAnalysisSeries:
            """
            Retrieves the ship location information from the specified protocol.

            Args:
                protocol (str): Radio protocol used by the ship.

            Returns:
                TheaterAnalysisSeries: The object containing ship location information.
            """
            try:
                return service.get_theater_analysis()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


        @app.get("/guerre_elec/sensor_data",
                 tags=fastapi_tags,
                 description="Get information on data captured by the sensor",
                 summary="Get information on data captured by the sensor"
                 )
        async def get_sensor_data(user: KeycloakUser = Depends(get_current_user)
                                         ) -> DetectedDataSeries:
            """
            Retrieves information on data captured by the sensor

            Returns:
                DetectedDataSeries: The object containing detected sensor data.
            """
            try:
                return service.get_sensor_data()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

        @app.get("/guerre_elec/active_ships",
                 tags=fastapi_tags,
                 description="Get data of active ships",
                 summary="Get data of active ships"
                 )
        async def get_active_ships(user: KeycloakUser = Depends(get_current_user)
                                         ) -> TheaterAnalysisSeries:
            """
            Retrieves the ship location information from the specified protocol.

            Returns:
                TheaterAnalysisSeries: The object containing ship information.
            """
            try:
                return service.get_active_ships()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")