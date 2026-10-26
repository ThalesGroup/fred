# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Person-authenticated Weaver metadata; never creates execution authority."""

from collections.abc import Mapping
from uuid import UUID

import httpx
from fastapi import HTTPException
from fred_core.security.structure import KeycloakUser, is_service_agent
from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition
from fred_sdk.contracts.skills import SkillCatalog, SkillDetail, SkillInvocation
from fred_sdk.contracts.weaver import WeaverRuntimeBinding
from pydantic import ValidationError

from fred_runtime.app.context import PodApplicationContext
from fred_runtime.runtime_context import get_runtime_context


async def get_instance_skills(
    agent_instance_id: str,
    team_id: str,
    caller: KeycloakUser | None,
    authorization: str | None,
    container: PodApplicationContext,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    *,
    space_id: str | None = None,
) -> SkillCatalog:
    """Read the public resolver projection with the person's own bearer only."""
    if caller is None or is_service_agent(caller) or not authorization:
        raise HTTPException(status_code=403, detail="Person credential required")
    try:
        space = str(UUID(space_id or ""))
        instance = str(UUID(agent_instance_id))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Canonical space and instance required"
        ) from None
    runtime = get_runtime_context().config
    if not runtime.control_plane_url:
        raise HTTPException(status_code=503, detail="Weaver resolver unavailable")
    try:
        response = await container.get_control_plane_http_client().get(
            f"{runtime.control_plane_url.rstrip('/')}/spaces/{space}/agent-instances/{instance}/runtime",
            headers={"Authorization": authorization},
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=403, detail="Weaver metadata refused")
        binding = WeaverRuntimeBinding.model_validate(response.json())
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=503, detail="Weaver metadata unavailable"
        ) from None
    if (
        binding.subject_id != caller.uid
        or str(binding.space.id) != space
        or str(binding.agent.instance_id) != instance
        or binding.agent.runtime_id != runtime.service_name
        or (str(binding.space.team_id) if binding.space.team_id else None) != team_id
    ):
        raise HTTPException(status_code=403, detail="Weaver metadata binding mismatch")
    definition = registry.get(binding.agent.template_key)
    if definition is None:
        raise HTTPException(status_code=409, detail="Resolved template is unavailable")
    if isinstance(definition, GraphAgentDefinition):
        return SkillCatalog(supported=False)
    skills = get_runtime_context().config.skills
    return skills.catalog if skills is not None else SkillCatalog()


async def get_instance_skill_detail(
    skill_name: str,
    agent_instance_id: str,
    team_id: str,
    caller: KeycloakUser | None,
    authorization: str | None,
    container: PodApplicationContext,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    *,
    space_id: str | None = None,
) -> SkillDetail:
    """Authorize through the catalog before reading its immutable snapshot."""
    catalog = await get_instance_skills(
        agent_instance_id,
        team_id,
        caller,
        authorization,
        container,
        registry,
        space_id=space_id,
    )
    try:
        name = SkillInvocation(name=skill_name).name
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid skill name") from None
    summary = next((skill for skill in catalog.skills if skill.name == name), None)
    skills = get_runtime_context().config.skills
    if not catalog.supported or summary is None or skills is None:
        raise HTTPException(status_code=404, detail="Skill preview unavailable")
    return SkillDetail(
        skill=summary, revision=catalog.revision, content=skills.read(name)
    )
