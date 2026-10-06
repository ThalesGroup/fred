# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Authenticated, team-scoped metadata for the actual managed instance."""

from collections.abc import Mapping

from fred_core.security.structure import KeycloakUser
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition
from fred_sdk.contracts.skills import SkillCatalog

from fred_runtime.app.context import PodApplicationContext
from fred_runtime.runtime_context import get_runtime_context


async def get_instance_skills(
    agent_instance_id: str,
    team_id: str,
    caller: KeycloakUser | None,
    authorization: str | None,
    container: PodApplicationContext,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
) -> SkillCatalog:
    """Reuse execution authorization/resolution without admitting an execution."""
    from fred_runtime.app.agent_app import (
        _authorize_execution_or_raise,
        _resolve_agent_instance,
        _to_internal_request,
        _validate_resolved_team,
    )
    from fred_runtime.common.outbound_credentials import static_person_provider

    request = RuntimeExecuteRequest(
        input="List available platform skills",
        agent_instance_id=agent_instance_id,
        runtime_context=RuntimeContext(team_id=team_id),
    )
    await _authorize_execution_or_raise(request, caller, container)
    token = authorization.removeprefix("Bearer ") if authorization else None
    target = await _resolve_agent_instance(
        request=_to_internal_request(request),
        registry=registry,
        access_token=token,
        control_plane_url=get_runtime_context().config.control_plane_url,
        http_client=container.get_control_plane_http_client(),
        team_id=team_id,
        credentials=static_person_provider(token),
    )
    _validate_resolved_team(request, target.team_id, container)
    if isinstance(target.definition, GraphAgentDefinition):
        return SkillCatalog(supported=False)
    skills = get_runtime_context().config.skills
    return skills.catalog if skills is not None else SkillCatalog()
