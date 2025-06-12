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
from services.mission.mission_abstract_service import AbstractMissionService
from services.mission.mission_service import MissionService
from services.mission.mission_structures import MissionSeries

class MissionController:
    def __init__(self, app: APIRouter):
        service: AbstractMissionService = MissionService()

        fastapi_tags = ["Mission"]

        @app.get("/guerre_elec/mission",
                 tags=fastapi_tags,
                 description="Get information on ongoing mission",
                 summary="Get information on ongoing mission"
                 )
        async def get_mission(user: KeycloakUser = Depends(get_current_user)
                                         ) -> MissionSeries:
            """
            Retrieves data from ongoing mission.
            
            Returns:
                MissionSeries: The object containing ship location information.
            """
            try:
                return service.get_mission()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")