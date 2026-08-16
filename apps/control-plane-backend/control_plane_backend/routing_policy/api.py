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

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.routing_policy.schemas import (
    AvailableModelProfileList,
    PlatformModelBinding,
    ProfileNotUsableError,
    SetPlatformModelBindingRequest,
    TeamRoutingPolicy,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.service import (
    delete_platform_model_binding as delete_platform_model_binding_from_service,
)
from control_plane_backend.routing_policy.service import (
    get_platform_model_binding as get_platform_model_binding_from_service,
)
from control_plane_backend.routing_policy.service import (
    get_team_routing_policy as get_team_routing_policy_from_service,
)
from control_plane_backend.routing_policy.service import (
    list_available_model_profiles as list_available_model_profiles_from_service,
)
from control_plane_backend.routing_policy.service import (
    set_platform_model_binding as set_platform_model_binding_from_service,
)
from control_plane_backend.routing_policy.service import (
    update_team_routing_policy as update_team_routing_policy_from_service,
)

router = APIRouter(tags=["Teams"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProfileNotUsableError)
    async def profile_not_usable_handler(
        _request, exc: ProfileNotUsableError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(UnknownProfileError)
    async def unknown_profile_handler(
        _request, exc: UnknownProfileError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@router.get(
    "/teams/{team_id}/routing-policy",
    response_model=TeamRoutingPolicy,
    response_model_exclude_none=True,
    summary="Get one team's LLM model routing policy (TEAM-05, #2118)",
)
async def get_team_routing_policy(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamRoutingPolicy:
    return await get_team_routing_policy_from_service(user, team_id, deps)


@router.get(
    "/teams/{team_id}/routing-policy/available-models",
    response_model=AvailableModelProfileList,
    summary="List model profiles this team is can_use-enabled for (routing-policy picker, TEAM-05.1, #2167)",
)
async def get_available_model_profiles(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> AvailableModelProfileList:
    return await list_available_model_profiles_from_service(user, team_id, deps)


@router.patch(
    "/teams/{team_id}/routing-policy",
    response_model=TeamRoutingPolicy,
    response_model_exclude_none=True,
    summary="Replace one team's LLM model routing policy (team_editor only, TEAM-05, #2118)",
)
async def update_team_routing_policy(
    team_id: Annotated[TeamId, Path()],
    request: UpdateTeamRoutingPolicyRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> TeamRoutingPolicy:
    return await update_team_routing_policy_from_service(user, team_id, request, deps)


@router.get(
    "/admin/platform/model-bindings",
    response_model=PlatformModelBinding,
    response_model_exclude_none=True,
    tags=["PlatformModelRouting"],
    summary="Get the platform-wide chat model binding (org admin, V1 chat-only).",
)
async def get_platform_model_binding(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformModelBinding:
    return await get_platform_model_binding_from_service(user=user, deps=deps)


@router.put(
    "/admin/platform/model-bindings",
    response_model=PlatformModelBinding,
    response_model_exclude_none=True,
    tags=["PlatformModelRouting"],
    summary="Set the platform-wide chat model binding (org admin, V1 chat-only).",
)
async def put_platform_model_binding(
    request: SetPlatformModelBindingRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformModelBinding:
    return await set_platform_model_binding_from_service(
        user=user,
        binding=request.binding,
        deps=deps,
    )


@router.delete(
    "/admin/platform/model-bindings",
    response_model=PlatformModelBinding,
    response_model_exclude_none=True,
    tags=["PlatformModelRouting"],
    summary="Unset the platform-wide chat model binding (org admin, V1 chat-only).",
)
async def delete_platform_model_binding(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformModelBinding:
    return await delete_platform_model_binding_from_service(user=user, deps=deps)
