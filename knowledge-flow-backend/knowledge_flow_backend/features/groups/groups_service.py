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

import asyncio
import logging
from collections.abc import Iterable
from typing import cast

from fred_core import (
    Action,
    GroupPermission,
    KeycloackDisabled,
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    RelationType,
    Resource,
    authorize,
    create_keycloak_admin,
)
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from knowledge_flow_backend.application_context import get_configuration, get_group_store, get_rebac_engine
from knowledge_flow_backend.features.groups.groups_structures import GroupProfile, GroupProfileUpdate, GroupSummary
from knowledge_flow_backend.features.users.users_service import get_users_by_ids
from knowledge_flow_backend.features.users.users_structures import UserSummary

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200
_DEFAULT_LIMIT = 10000


@authorize(Action.READ, Resource.GROUP)
async def list_groups(
    user: KeycloakUser,
    *,
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
    member_only: bool = True,
) -> list[GroupSummary]:
    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty group list.")
        return []

    root_groups = await _fetch_root_groups(admin)
    groups: list[GroupSummary] = []

    for raw_group in root_groups:
        group_id = raw_group.get("id")
        if not group_id:
            logger.debug("Skipping Keycloak group without identifier: %s", raw_group)
            continue
        group = await _build_group_summary(admin, group_id)
        if group:
            groups.append(group)

    group_ids = _collect_group_ids(groups)
    profiles = _fetch_group_profiles(group_ids)
    owners = await _fetch_group_owners(group_ids)
    is_admin = "admin" in user.roles
    readable_group_ids = set() if is_admin else await _fetch_readable_group_ids(user)
    member_group_ids = await _resolve_user_group_ids(admin, user)

    _apply_group_metadata(groups, profiles, owners, member_group_ids)

    filtered = [
        group
        for group in groups
        if _is_group_visible(
            group,
            is_admin=is_admin,
            member_only=member_only,
            readable_group_ids=readable_group_ids,
        )
    ]

    if offset < 0:
        offset = 0
    if limit <= 0:
        return filtered[offset:]
    return filtered[offset : offset + limit]


@authorize(Action.UPDATE, Resource.GROUP)
async def upsert_group_profile(
    user: KeycloakUser,
    group_id: str,
    payload: GroupProfileUpdate,
) -> GroupProfile:
    """
    Store group profile data (description, banner, privacy) with ReBAC check.
    """
    rebac = get_rebac_engine()
    await rebac.check_user_permission_or_raise(user, GroupPermission.UPDATE_INFO, group_id)

    store = get_group_store()
    if store is None:
        raise ValueError("No group store configured.")

    existing = store.get_group_profile(group_id) or GroupProfile(id=group_id)

    updated = existing.model_copy(
        update=payload.model_dump(exclude_unset=True),
    )
    store.upsert_group_profile(updated)
    return updated


async def get_groups_by_ids(group_ids: Iterable[str]) -> dict[str, GroupSummary]:
    """
    Fetch hierarchical summaries for the provided group ids.
    Falls back to id-only summaries when Keycloak data cannot be retrieved.
    """
    unique_ids = {group_id for group_id in group_ids if group_id}
    if not unique_ids:
        return {}

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning fallback group profiles.")
        return {}

    ordered_ids = sorted(unique_ids)

    coroutines = {group_id: _build_group_summary(admin, group_id) for group_id in ordered_ids}
    results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    summaries: dict[str, GroupSummary] = {}
    for group_id, result in zip(coroutines.keys(), results):
        if isinstance(result, BaseException):
            if isinstance(result, KeycloakGetError) and result.response_code == 404:
                logger.debug("Group %s not found in Keycloak.", group_id)
                continue
            raise result

        summary = cast(GroupSummary | None, result)
        if summary:
            summaries[group_id] = summary
    return summaries


async def _fetch_root_groups(admin: KeycloakAdmin) -> list[dict]:
    groups: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _GROUP_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        groups.extend(batch)
        if len(batch) < _GROUP_PAGE_SIZE:
            break

        offset += _GROUP_PAGE_SIZE

    return groups


async def _build_group_summary(admin: KeycloakAdmin, group_id: str) -> GroupSummary | None:
    detailed_group = await admin.a_get_group(group_id)
    if not detailed_group:
        logger.debug("Keycloak returned empty group payload for id %s", group_id)
        return None

    direct_members = await _fetch_group_member_ids(admin, group_id)

    return GroupSummary(
        id=group_id,
        name=_sanitize_name(detailed_group.get("name"), fallback=group_id),
        member_count=len(direct_members),
        description=_extract_group_description(detailed_group),
    )


def _sanitize_name(value: object, fallback: str) -> str:
    name = (str(value or "")).strip()
    return name or fallback


def _extract_group_description(payload: dict) -> str | None:
    raw_description = payload.get("description")
    if raw_description:
        text = str(raw_description).strip()
        if text:
            return text
    attributes = payload.get("attributes") or {}
    raw_attr = attributes.get("description")
    if isinstance(raw_attr, list):
        raw_attr = raw_attr[0] if raw_attr else None
    if raw_attr is None:
        return None
    text = str(raw_attr).strip()
    return text or None


async def _fetch_group_member_ids(admin: KeycloakAdmin, group_id: str) -> set[str]:
    member_ids: set[str] = set()
    offset = 0

    while True:
        batch = await admin.a_get_group_members(group_id, {"first": offset, "max": _MEMBER_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        for member in batch:
            member_id = member.get("id")
            if member_id:
                member_ids.add(member_id)
        if len(batch) < _MEMBER_PAGE_SIZE:
            break

        offset += _MEMBER_PAGE_SIZE

    return member_ids


def _collect_group_ids(groups: Iterable[GroupSummary]) -> list[str]:
    return [group.id for group in groups]


def _fetch_group_profiles(group_ids: Iterable[str]) -> dict[str, GroupProfile]:
    store = get_group_store()
    if store is None:
        return {}
    return store.list_group_profiles(group_ids)


async def _fetch_group_owners(group_ids: Iterable[str]) -> dict[str, list[UserSummary]]:
    ids = [group_id for group_id in group_ids if group_id]
    if not ids:
        return {}

    rebac = get_rebac_engine()
    if getattr(rebac, "enabled", True) is False:
        return {}

    coroutines = {
        group_id: rebac.lookup_subjects(
            RebacReference(type=Resource.GROUP, id=group_id),
            RelationType.OWNER,
            Resource.USER,
        )
        for group_id in ids
    }
    results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    owners_by_group: dict[str, list[str]] = {}
    owner_ids: set[str] = set()
    for group_id, result in zip(coroutines.keys(), results):
        if isinstance(result, BaseException):
            logger.debug("Failed to fetch owners for group %s: %s", group_id, result)
            owners_by_group[group_id] = []
            continue
        if isinstance(result, RebacDisabledResult):
            owners_by_group[group_id] = []
            continue
        ids_for_group = [ref.id for ref in result if ref.type == Resource.USER]
        owners_by_group[group_id] = ids_for_group
        owner_ids.update(ids_for_group)

    user_summaries = await get_users_by_ids(owner_ids)

    return {group_id: [user_summaries.get(owner_id) or UserSummary(id=owner_id) for owner_id in owner_ids_for_group] for group_id, owner_ids_for_group in owners_by_group.items()}


async def _fetch_readable_group_ids(user: KeycloakUser) -> set[str]:
    rebac = get_rebac_engine()
    if getattr(rebac, "enabled", True) is False:
        return set()

    try:
        result = await rebac.lookup_user_resources(user, GroupPermission.MEMBER)
    except Exception as exc:
        logger.debug("Failed to fetch readable groups from ReBAC: %s", exc)
        return set()

    if isinstance(result, RebacDisabledResult):
        return set()

    return {ref.id for ref in result if ref.type == Resource.GROUP}


async def _resolve_user_group_ids(admin: KeycloakAdmin, user: KeycloakUser) -> set[str]:
    raw_paths = [str(path).strip() for path in (user.groups or []) if str(path).strip()]
    if not raw_paths:
        return set()

    normalized_paths = set()
    for path in raw_paths:
        normalized = _normalize_group_path(path)
        if not normalized:
            continue
        normalized_paths.add(normalized)

    if not normalized_paths:
        return set()

    coroutines = {path: admin.a_get_group_by_path(path) for path in sorted(normalized_paths)}
    results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    group_ids: set[str] = set()
    for path, result in zip(coroutines.keys(), results):
        if isinstance(result, BaseException):
            if isinstance(result, KeycloakGetError) and result.response_code == 404:
                logger.debug("Group path %s not found in Keycloak.", path)
                continue
            logger.debug("Failed to resolve group path %s: %s", path, result)
            continue
        if not isinstance(result, dict):
            continue
        group_id = result.get("id")
        if group_id:
            group_ids.add(group_id)

    return group_ids


def _normalize_group_path(path: str) -> str:
    return "/".join(segment for segment in path.strip("/").split("/") if segment)


def _apply_group_metadata(
    groups: Iterable[GroupSummary],
    profiles: dict[str, GroupProfile],
    owners: dict[str, list[UserSummary]],
    member_group_ids: set[str],
) -> None:
    for group in groups:
        profile = profiles.get(group.id)
        if profile:
            if profile.description is not None:
                group.description = profile.description
            group.banner_image_url = profile.banner_image_url
            if profile.is_private is not None:
                group.is_private = profile.is_private
        group.owners = owners.get(group.id, [])
        group.is_member = group.id in member_group_ids


def _is_group_visible(
    group: GroupSummary,
    *,
    is_admin: bool,
    member_only: bool,
    readable_group_ids: set[str],
) -> bool:
    if is_admin:
        return True
    if member_only:
        return bool(group.is_member)
    if group.is_private is True:
        return group.id in readable_group_ids or bool(group.is_member)
    if group.is_private is False:
        return True
    return True
