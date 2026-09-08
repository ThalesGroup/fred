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

from control_plane_backend.platform_prompt.schemas import (
    PlatformInstructions,
    PlatformPrompt,
    SetPlatformPromptRequest,
)
from control_plane_backend.platform_prompt.service import (
    get_platform_instructions as get_platform_instructions_from_service,
)
from control_plane_backend.platform_prompt.service import (
    get_platform_prompt as get_platform_prompt_from_service,
)
from control_plane_backend.platform_prompt.service import (
    set_platform_prompt as set_platform_prompt_from_service,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["PlatformPrompt"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.get(
    "/admin/platform/prompt",
    response_model=PlatformPrompt,
    summary="Get the platform-wide platform prompt (org admin).",
)
async def get_platform_prompt(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformPrompt:
    return await get_platform_prompt_from_service(user=user, deps=deps)


@router.put(
    "/admin/platform/prompt",
    response_model=PlatformPrompt,
    summary="Set the platform-wide platform prompt (org admin).",
)
async def put_platform_prompt(
    request: SetPlatformPromptRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformPrompt:
    return await set_platform_prompt_from_service(
        user=user, text=request.text, deps=deps
    )


@router.get(
    "/admin/platform/instructions",
    response_model=PlatformInstructions,
    summary="Get the read-only platform operating instructions (org admin).",
)
async def get_platform_instructions(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformInstructions:
    return await get_platform_instructions_from_service(user=user, deps=deps)
