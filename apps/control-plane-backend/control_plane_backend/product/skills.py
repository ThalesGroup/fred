# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Resolve skill metadata only from a managed instance's configured source."""

import httpx
from fred_core.common import TeamId
from fred_sdk.contracts.skills import SkillCatalog, SkillDetail, SkillInvocation
from pydantic import ValidationError

from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.service import ExecutionPreparationError


async def _get_instance_skill_response(
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
    authorization: str | None,
    skill_name: str | None = None,
) -> httpx.Response:
    """Resolve the selected source for catalog and read-only detail requests."""
    instance = await deps.get_agent_instance_store().get_for_team(
        agent_instance_id, team_id
    )
    if instance is None:
        raise ExecutionPreparationError(
            "Unknown agent instance for this team", http_status=404
        )
    if not instance.enabled or instance.suspension_reason is not None:
        raise ExecutionPreparationError("Agent instance unavailable", http_status=409)
    source = next(
        (
            source
            for source in deps.configuration.platform.runtime_catalog_sources
            if source.enabled and source.runtime_id == instance.source_runtime_id
        ),
        None,
    )
    if source is None:
        raise ExecutionPreparationError("Runtime source unavailable", http_status=503)
    if skill_name is not None:
        try:
            skill_name = SkillInvocation(name=skill_name).name
        except ValidationError:
            raise ExecutionPreparationError(
                "Invalid skill name", http_status=422
            ) from None
    suffix = f"/{skill_name}" if skill_name is not None else ""
    try:
        response = await deps.get_runtime_http_client().get(
            f"{source.base_url.rstrip('/')}/agents/skills{suffix}",
            params={"agent_instance_id": agent_instance_id, "team_id": str(team_id)},
            headers={"Authorization": authorization} if authorization else None,
            timeout=10.0,
        )
        if response.status_code == 404 and skill_name is None:
            return response
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        raise ExecutionPreparationError(
            "Runtime skill catalog unavailable",
            http_status=exc.response.status_code
            if exc.response.status_code in {401, 403, 404, 409, 422}
            else 502,
        ) from None
    except (ValidationError, ValueError):
        raise ExecutionPreparationError(
            "Invalid runtime skill catalog", http_status=502
        ) from None
    except httpx.RequestError:
        raise ExecutionPreparationError(
            "Runtime skill catalog unreachable", http_status=503
        ) from None


async def get_instance_skills(
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
    authorization: str | None = None,
) -> SkillCatalog:
    response = await _get_instance_skill_response(
        team_id, agent_instance_id, deps, authorization
    )
    if response.status_code == 404:
        return SkillCatalog(supported=False)
    try:
        return SkillCatalog.model_validate(response.json())
    except (ValidationError, ValueError):
        raise ExecutionPreparationError(
            "Invalid runtime skill catalog", http_status=502
        ) from None


async def get_instance_skill_detail(
    team_id: TeamId,
    agent_instance_id: str,
    skill_name: str,
    deps: ProductServiceDependencies,
    authorization: str | None = None,
) -> SkillDetail:
    response = await _get_instance_skill_response(
        team_id, agent_instance_id, deps, authorization, skill_name
    )
    try:
        detail = SkillDetail.model_validate(response.json())
        if detail.skill.name != skill_name:
            raise ValueError("Mismatched skill detail")
        return detail
    except (ValidationError, ValueError):
        raise ExecutionPreparationError(
            "Invalid runtime skill detail", http_status=502
        ) from None
