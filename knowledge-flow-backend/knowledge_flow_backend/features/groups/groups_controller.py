from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.groups.groups_service import (
    list_groups as list_groups_from_service,
    upsert_group_profile as upsert_group_profile_from_service,
    add_group_relation as add_group_relation_from_service,
)
from knowledge_flow_backend.features.groups.groups_structures import GroupProfile, GroupProfileUpdate, GroupRelationRequest, GroupSummary

router = APIRouter(tags=["Groups"])


@router.get(
    "/groups",
    response_model=list[GroupSummary],
    response_model_exclude_none=True,
    summary="List groups registered in Keycloak.",
)
async def list_groups(
    limit: Annotated[int, Query(ge=1, le=10000, description="Max items to return")] = 10000,
    offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
    member_only: Annotated[bool, Query(description="Only groups the user belongs to")] = True,
    user: KeycloakUser = Depends(get_current_user),
) -> list[GroupSummary]:
    return await list_groups_from_service(user, limit=limit, offset=offset, member_only=member_only)


@router.post(
    "/groups/{group_id}/relations",
    status_code=204,
    summary="Add a user/group relation to a group (member/manager/owner)",
)
async def add_group_relation(
    group_id: str,
    payload: GroupRelationRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    await add_group_relation_from_service(user, group_id, payload)


@router.put(
    "/groups/{group_id}/profile",
    response_model=GroupProfile,
    summary="Create or update a group profile (description, banner, privacy)",
)
async def upsert_group_profile(
    group_id: str,
    payload: GroupProfileUpdate,
    user: KeycloakUser = Depends(get_current_user),
) -> GroupProfile:
    return await upsert_group_profile_from_service(user, group_id, payload)
