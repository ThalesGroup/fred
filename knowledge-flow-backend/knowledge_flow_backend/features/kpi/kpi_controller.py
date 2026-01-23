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

import logging

from fastapi import APIRouter, Depends
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from fred_core.kpi import FilterTerm, KPIQuery, KPIQueryResult

from knowledge_flow_backend.application_context import get_app_context

logger = logging.getLogger(__name__)


class KPIController:
    """
    Minimal controller exposing a single KPI query endpoint.
    Uses the fred_core reader abstraction.
    """

    def __init__(
        self,
        router: APIRouter,
    ):
        # Init the writer store (creates index if needed)

        # Reader wraps the same OS client + index
        self.reader = get_app_context().get_kpi_store()

        @router.post("/kpi/query", response_model=KPIQueryResult, tags=["KPI"])
        async def query(body: KPIQuery, user: KeycloakUser = Depends(get_current_user)):
            if body.view_global:
                authorize_or_raise(user, Action.READ_GLOBAL, Resource.KPIS)
                logger.info("[KPI][QUERY] Global view requested by user_id=%s. Not applying user filter.", user.uid)
            else:
                authorize_or_raise(user, Action.READ, Resource.KPIS)
                logger.info("[KPI][QUERY] Applying user filter for user_id=%s", user.uid)
                body.filters.append(FilterTerm(field="dims.user_id", value=user.uid))

            return self.reader.query(body)
