# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Global packaged skills under Administration > Features."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.platform_skills import service
from control_plane_backend.platform_skills.schemas import (
    PlatformSkillEnabled,
    PlatformSkillInventory,
    PlatformSkillPolicy,
    SetPlatformSkillEnabledRequest,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["PlatformSkills"])
ProductDependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


@router.get(
    "/platform/skills",
    response_model=PlatformSkillInventory,
    operation_id="get_platform_skills",
)
async def get_platform_skills(
    deps: ProductDependencies,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformSkillInventory:
    """List packaged skills and source diagnostics for a feature manager."""
    return await service.get_platform_skills(
        user=user, deps=deps, authorization=request.headers.get("Authorization")
    )


@router.get(
    "/platform/skills/policy",
    response_model=PlatformSkillPolicy,
    operation_id="get_platform_skill_policy",
)
async def get_platform_skill_policy(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformSkillPolicy:
    """Expose restriction names to authenticated callers for direct runtime turns."""
    return await service.get_platform_skill_policy(deps)


@router.put(
    "/platform/skills/{skill_name}",
    response_model=PlatformSkillEnabled,
    operation_id="set_platform_skill_enabled",
)
async def set_platform_skill_enabled(
    skill_name: Annotated[
        str, Path(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    ],
    body: SetPlatformSkillEnabledRequest,
    deps: ProductDependencies,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
) -> PlatformSkillEnabled:
    """Apply one feature-manager decision globally for subsequent turns."""
    return await service.set_platform_skill_enabled(
        user=user,
        name=skill_name,
        enabled=body.enabled,
        deps=deps,
        authorization=request.headers.get("Authorization"),
    )
