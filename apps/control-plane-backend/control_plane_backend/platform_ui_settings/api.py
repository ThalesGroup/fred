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
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.platform_ui_settings.schemas import (
    PlatformUiSettings,
    SetPlatformUiSettingsRequest,
)
from control_plane_backend.platform_ui_settings.service import (
    get_platform_ui_settings as get_platform_ui_settings_from_service,
)
from control_plane_backend.platform_ui_settings.service import (
    set_platform_ui_settings as set_platform_ui_settings_from_service,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["PlatformUiSettings"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.get(
    "/admin/platform/ui-settings",
    response_model=PlatformUiSettings,
    summary="Get the platform UI theme settings (platform admin).",
)
async def get_platform_ui_settings(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformUiSettings:
    return await get_platform_ui_settings_from_service(user=user, deps=deps)


@router.put(
    "/admin/platform/ui-settings",
    response_model=PlatformUiSettings,
    summary="Replace the platform UI theme settings (platform admin).",
)
async def put_platform_ui_settings(
    request: SetPlatformUiSettingsRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformUiSettings:
    return await set_platform_ui_settings_from_service(
        user=user, request=request, deps=deps
    )
