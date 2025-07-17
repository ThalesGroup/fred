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
from datetime import datetime

from fastapi import Depends, HTTPException, Query, APIRouter

from fred_core import KeycloakUser, get_current_user
from app.features.frugal.cluster_consumption.cluster_consumption_abstract_service import AbstractClusterConsumptionService
from app.features.frugal.cluster_consumption.cluster_consumption_service import ClusterConsumptionService
from app.features.frugal.cluster_consumption.cluster_consumption_structures import ClusterConsumptionSeries
from app.common.structure import CompareResult
from app.common.structure import PrecisionEnum
from app.common.utils import API_COMPARE_DOC


class EnergyController:
    def __init__(self, app: APIRouter):
        service: AbstractClusterConsumptionService = ClusterConsumptionService()

        fastapi_tags = ["Energy footprint"]

        @app.get("/energy/consumption/",
                 tags=fastapi_tags,
                 description="Get the energy consumption for a given time range",
                 summary="Get the energy consumption for a given time range"
                 )
        async def get_energy_consumption(start: datetime, end: datetime,
                                         cluster: str,
                                         precision: PrecisionEnum = PrecisionEnum.NONE,
                                         user: KeycloakUser = Depends(get_current_user)
                                         ) -> ClusterConsumptionSeries:
            try:
                return service.consumption_wh(start, end, cluster, precision)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/energy/mix",
                 tags=fastapi_tags,
                 description="Get the energy consumption mix for a given time range",
                 summary="Get the energy consumption mix for a given time range"
                 )
        async def get_energy_mix(start: datetime, end: datetime,
                                 precision: PrecisionEnum = PrecisionEnum.D,
                                 user: KeycloakUser = Depends(get_current_user)
                                 ) -> ClusterConsumptionSeries:
            try:
                return service.consumption_mix(start, end, precision)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/energy/consumption/compare",
                 tags=fastapi_tags,
                 summary="Compare two windows of energy consumption for a given cluster and time ranges",
                 description=API_COMPARE_DOC,
                 )
        async def get_compare_energy_consumption(
                start_window_1: datetime = Query(..., description="Start datetime of the first window"),
                end_window_1: datetime = Query(..., description="End datetime of the first window"),
                start_window_2: datetime = Query(..., description="Start datetime of the second window"),
                end_window_2: datetime = Query(..., description="End datetime of the second window"),
                cluster: str = Query(..., description="The measured cluster"),
                user: KeycloakUser = Depends(get_current_user)
        ) -> CompareResult:
            try:
                return service.consumption_wh_compare(start_window_1, end_window_1, start_window_2, end_window_2,
                                                      cluster)
            except ValueError as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internally invalid data: {e}")
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))
