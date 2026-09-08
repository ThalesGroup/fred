# Copyright Thales 2026
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

"""Collaborative-team application catalog route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.app.feature_flags import require_feature_enabled
from control_plane_backend.applications.schemas import ApplicationList
from control_plane_backend.applications.service import list_team_applications
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(
    tags=["Applications"],
    dependencies=[Depends(require_feature_enabled("enableApplications"))],
)
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.get(
    "/teams/{team_id}/applications",
    response_model=ApplicationList,
    summary="List installed applications available to the selected team.",
)
async def get_team_applications(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ApplicationList:
    return await list_team_applications(user=user, team_id=team_id, deps=deps)
