# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Discover packaged skills from configured runtimes for feature managers."""

import asyncio
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from fred_core import KeycloakUser
from fred_core.logs.audit_log import emit_audit_log
from fred_sdk.contracts.skills import SkillCatalog, SkillInvocation
from pydantic import ValidationError

from control_plane_backend.config.models import RuntimeCatalogSourceConfig
from control_plane_backend.organization_authz import require_manage_capabilities
from control_plane_backend.platform_skills.schemas import (
    PlatformSkillEnabled,
    PlatformSkillEntry,
    PlatformSkillInventory,
    PlatformSkillPolicy,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies


@dataclass(frozen=True)
class _RuntimeCatalog:
    runtime_id: str
    catalog: SkillCatalog | None = None
    unsupported: bool = False


async def _fetch_catalog(
    source: RuntimeCatalogSourceConfig,
    client: httpx.AsyncClient,
    authorization: str | None,
) -> _RuntimeCatalog:
    """Fetch only this configured source, with bounded I/O and no redirects."""
    try:
        response = await client.get(
            f"{source.base_url.rstrip('/')}/agents/platform-skills",
            headers={"Authorization": authorization} if authorization else None,
            timeout=5.0,
            follow_redirects=False,
        )
        if response.status_code == 404:
            return _RuntimeCatalog(source.runtime_id, unsupported=True)
        response.raise_for_status()
        catalog = SkillCatalog.model_validate(response.json())
        for skill in catalog.skills:
            SkillInvocation(name=skill.name)
        return _RuntimeCatalog(
            source.runtime_id, catalog, unsupported=not catalog.policy_supported
        )
    except (httpx.HTTPError, ValidationError, ValueError):
        return _RuntimeCatalog(source.runtime_id)


async def get_platform_skills(
    *,
    user: KeycloakUser,
    deps: ProductServiceDependencies,
    authorization: str | None = None,
) -> PlatformSkillInventory:
    """List global packaged metadata after the feature-management permission gate."""
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    return await _get_inventory(deps, authorization)


async def _get_inventory(
    deps: ProductServiceDependencies, authorization: str | None
) -> PlatformSkillInventory:
    """Share one live catalog and policy computation between listing and writes."""
    sources = [
        source
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
    ]
    catalogs, disabled = await asyncio.gather(
        asyncio.gather(
            *(
                _fetch_catalog(source, deps.get_runtime_http_client(), authorization)
                for source in sources
            )
        ),
        deps.get_platform_skill_policy_store().list_disabled_skill_names(),
    )
    entries: dict[str, PlatformSkillEntry] = {}
    result = PlatformSkillInventory(disabled_skill_names=sorted(disabled))
    for source in catalogs:
        if source.unsupported:
            result.unsupported_runtime_ids.append(source.runtime_id)
        elif source.catalog is None:
            result.unavailable_runtime_ids.append(source.runtime_id)
        if source.catalog is None:
            continue
        for skill in source.catalog.skills:
            if not skill.builtin:
                continue
            entry = entries.setdefault(
                skill.name,
                PlatformSkillEntry(skill=skill, enabled=skill.name not in disabled),
            )
            entry.runtime_ids.append(source.runtime_id)
    result.skills = [entries[name] for name in sorted(entries)]
    for entry in result.skills:
        entry.runtime_ids.sort()
    result.unavailable_runtime_ids.sort()
    result.unsupported_runtime_ids.sort()
    return result


async def get_platform_skill_policy(
    deps: ProductServiceDependencies,
) -> PlatformSkillPolicy:
    """Read only names for authenticated runtimes, without exposing admin metadata."""
    disabled = await deps.get_platform_skill_policy_store().list_disabled_skill_names()
    return PlatformSkillPolicy(disabled_skill_names=sorted(disabled))


async def set_platform_skill_enabled(
    *,
    user: KeycloakUser,
    name: str,
    enabled: bool,
    deps: ProductServiceDependencies,
    authorization: str | None = None,
) -> PlatformSkillEnabled:
    """Validate and save one global state; allow recovery of stored names offline."""
    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    try:
        SkillInvocation(name=name)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid skill name") from None
    store = deps.get_platform_skill_policy_store()
    # An already enabled row is known too: retrying a lost recovery response
    # must keep succeeding even when every runtime source is unavailable.
    known_recovery = enabled and await store.get_enabled(name) is not None
    if not known_recovery:
        inventory = await _get_inventory(deps, authorization)
        if not enabled:
            if inventory.unsupported_runtime_ids:
                raise HTTPException(
                    status_code=409,
                    detail="Upgrade all runtime sources before disabling platform skills",
                )
            if inventory.unavailable_runtime_ids:
                raise HTTPException(
                    status_code=503,
                    detail="All runtime sources must be reachable before disabling platform skills",
                )
        if name not in {entry.skill.name for entry in inventory.skills}:
            raise HTTPException(
                status_code=404, detail="Unknown packaged platform skill"
            )
    await store.set_enabled(name=name, enabled=enabled, updated_by=user.uid)
    emit_audit_log(
        "platform.skill.activation_updated",
        actor_uid=user.uid,
        skill_name=name,
        enabled=enabled,
    )
    return PlatformSkillEnabled(name=name, enabled=enabled)
