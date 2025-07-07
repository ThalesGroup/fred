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
Controllers to expose the radio data endpoints
"""
import traceback
from fastapi import Depends, HTTPException, APIRouter

from app.security.keycloak import KeycloakUser, get_current_user
from app.services.theorical_radio.theorical_radio_abstract_service import AbstractTheoricalRadioService
from app.services.theorical_radio.theorical_radio_service import TheoricalRadioService
from app.services.theorical_radio.theorical_radio_structures import TheoricalRadioSeries

class TheoricalRadioController:
    def __init__(self, app: APIRouter):
        service: AbstractTheoricalRadioService = TheoricalRadioService()

        fastapi_tags = ["Theorical radio data"]

        @app.get("/guerre_elec/theorical_radio",
                 tags=fastapi_tags,
                 description="Get information on theorical radio data",
                 summary="Get information on theorical radio data"
                 )
        async def get_radio_data(user: KeycloakUser = Depends(get_current_user)
                                         ) -> TheoricalRadioSeries:
            """
            Retrieves theorical radio data.
            
            Returns:
                TheoricalRadioSeries: The object containing the radio data information.
            """
            try:
                return service.get_radio_data()
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")