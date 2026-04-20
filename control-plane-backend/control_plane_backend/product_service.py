from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fred_core import KeycloakUser, RBACProvider
from fred_core.common import PERSONAL_TEAM_ID, TeamId
from fred_sdk.contracts.execution import ExecutionGrant, ExecutionGrantAction

from control_plane_backend.agent_instance_store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.common.structures import ManagedAgentTuning
from control_plane_backend.product_structures import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PermissionSummary,
)
from control_plane_backend.teams_service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams_service import list_teams as list_teams_from_service
from control_plane_backend.users_structures import UserSummary

logger = logging.getLogger(__name__)

_rbac_provider = RBACProvider()


class _RuntimeTemplatePayload:
    """Runtime `/agents/templates` payload consumed by control-plane aggregation."""

    def __init__(
        self,
        *,
        template_agent_id: str,
        title: str,
        description: str,
        kind: str,
    ) -> None:
        self.template_agent_id = template_agent_id
        self.title = title
        self.description = description
        self.kind = kind

    @classmethod
    def model_validate(cls, data: dict) -> "_RuntimeTemplatePayload":
        return cls(
            template_agent_id=data["template_agent_id"],
            title=data["title"],
            description=data["description"],
            kind=data["kind"],
        )


def _build_permission_summary(user: KeycloakUser) -> PermissionSummary:
    items = _rbac_provider.list_permissions_for_user(user)
    allowed = set(items)
    return PermissionSummary(
        items=items,
        can_view_team_agents="agents:read" in allowed,
        can_manage_team_agents=bool(
            {"agents:create", "agents:update", "agents:delete"} & allowed
        ),
        can_manage_mcp_servers=bool(
            {
                "mcp_servers:create",
                "mcp_servers:update",
                "mcp_servers:delete",
            }
            & allowed
        ),
        can_view_feedback="feedback:read" in allowed,
        can_submit_feedback="feedback:create" in allowed,
        can_create_sessions="sessions:create" in allowed,
    )


async def build_frontend_bootstrap(user: KeycloakUser) -> FrontendBootstrap:
    """Build the frontend bootstrap from the shared selectable-team services.

    Why this function exists:
    - bootstrap should consume the same team resolution contract as `/teams` and
      `/teams/{team_id}` so `personal` is not shaped differently per endpoint

    How to use it:
    - call from the frontend bootstrap controller after authentication

    Example:
    - `payload = await build_frontend_bootstrap(user)`
    """

    app_context = ApplicationContext.get_instance()
    active_team, available_teams = await asyncio.gather(
        get_team_by_id_from_service(user, PERSONAL_TEAM_ID),
        list_teams_from_service(user),
    )
    return FrontendBootstrap(
        current_user=UserSummary.from_keycloak_user(user),
        active_team=active_team,
        available_teams=available_teams,
        feature_flags=app_context.configuration.platform.frontend.feature_flags,
        ui_settings=app_context.configuration.platform.frontend.ui_settings,
        permissions=_build_permission_summary(user),
    )


async def _fetch_runtime_templates(base_url: str) -> list[_RuntimeTemplatePayload]:
    url = f"{base_url.rstrip('/')}/agents/templates"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    return [_RuntimeTemplatePayload.model_validate(item) for item in payload]


async def list_agent_templates(team_id: TeamId) -> list[AgentTemplateSummary]:
    """Aggregate template summaries from all enabled configured runtime pods."""
    app_context = ApplicationContext.get_instance()
    templates: list[AgentTemplateSummary] = []
    for source in app_context.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            runtime_templates = await _fetch_runtime_templates(source.base_url)
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Failed to fetch runtime templates from %s for team %s: %s",
                source.base_url,
                team_id,
                exc,
            )
            continue

        for template in runtime_templates:
            templates.append(
                AgentTemplateSummary(
                    template_id=f"{source.runtime_id}:{template.template_agent_id}",
                    source_runtime_id=source.runtime_id,
                    source_agent_id=template.template_agent_id,
                    display_name=template.title,
                    description=template.description,
                    category=template.kind,
                    capabilities=[template.kind],
                )
            )
    return templates


async def list_managed_agent_instances(
    team_id: TeamId,
) -> list[ManagedAgentInstanceSummary]:
    """Return the enrolled managed agent instances for one team from the DB."""
    store: AgentInstanceStore = (
        ApplicationContext.get_instance().get_agent_instance_store()
    )
    records = await store.list_by_team(team_id)
    return [
        ManagedAgentInstanceSummary(
            agent_instance_id=record.agent_instance_id,
            team_id=record.team_id,
            template_id=record.template_id,
            display_name=record.display_name,
            description=record.description,
            status="enabled" if record.enabled else "disabled",
            created_at=record.created_at,
            updated_at=record.updated_at,
            created_by=record.created_by,
        )
        for record in records
    ]


_EXECUTION_GRANT_TTL_SECONDS = 300  # 5 minutes


class ExecutionPreparationError(Exception):
    """Raised when execution preparation cannot be completed."""

    def __init__(self, message: str, *, http_status: int = 404) -> None:
        super().__init__(message)
        self.http_status = http_status


class EnrollmentError(Exception):
    """Raised when agent instance enrollment fails."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


async def enroll_agent_instance(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateAgentInstanceRequest,
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for a team, creating a DB-backed managed instance.

    template_id must be '{source_runtime_id}:{source_agent_id}'.
    The runtime source must be configured and enabled.
    Any discovered template can be enrolled — no admin approval required.
    """
    parts = request.template_id.split(":", 1)
    if len(parts) != 2:
        raise EnrollmentError(
            f"Invalid template_id {request.template_id!r}. "
            "Expected format: '{source_runtime_id}:{source_agent_id}'."
        )
    source_runtime_id, source_agent_id = parts

    app_context = ApplicationContext.get_instance()
    source = next(
        (
            s
            for s in app_context.configuration.platform.runtime_catalog_sources
            if s.runtime_id == source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise EnrollmentError(
            f"Runtime source {source_runtime_id!r} is not available or not enabled.",
            http_status=404,
        )

    agent_instance_id = str(uuid4())
    tuning = ManagedAgentTuning(
        role=request.display_name,
        description=request.description or request.display_name,
    )
    record = AgentInstanceRecord(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        template_id=request.template_id,
        source_runtime_id=source_runtime_id,
        source_agent_id=source_agent_id,
        display_name=request.display_name,
        description=request.description,
        enabled=True,
        created_by=user.uid,
        tuning=tuning,
    )

    store: AgentInstanceStore = app_context.get_agent_instance_store()
    created = await store.create(record)
    return ManagedAgentInstanceSummary(
        agent_instance_id=created.agent_instance_id,
        team_id=created.team_id,
        template_id=created.template_id,
        display_name=created.display_name,
        description=created.description,
        status="enabled" if created.enabled else "disabled",
        created_at=created.created_at,
        updated_at=created.updated_at,
        created_by=created.created_by,
    )


async def unenroll_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
) -> bool:
    """
    Unenroll (delete) one managed agent instance for a team.

    Returns True if the record was found and deleted, False if not found.
    """
    store: AgentInstanceStore = (
        ApplicationContext.get_instance().get_agent_instance_store()
    )
    return await store.delete(agent_instance_id, team_id)


async def prepare_execution(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
) -> ExecutionPreparation:
    """
    Prepare one authorized runtime execution context for one managed agent instance.

    Raises ExecutionPreparationError when the instance is unknown, disabled,
    or when its runtime source is not configured with an ingress prefix.
    """
    app_context = ApplicationContext.get_instance()
    store: AgentInstanceStore = app_context.get_agent_instance_store()

    instance = await store.get_for_team(agent_instance_id, team_id)
    if instance is None:
        raise ExecutionPreparationError(
            f"Unknown agent instance {agent_instance_id!r} for team {team_id!r}."
        )
    if not instance.enabled:
        raise ExecutionPreparationError(
            f"Agent instance {agent_instance_id!r} is disabled.",
            http_status=409,
        )

    source = next(
        (
            s
            for s in app_context.configuration.platform.runtime_catalog_sources
            if s.runtime_id == instance.source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} is not available.",
            http_status=503,
        )
    if not source.ingress_prefix:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} has no ingress_prefix "
            "configured. Set ingress_prefix in platform.runtime_catalog_sources.",
            http_status=503,
        )

    prefix = source.ingress_prefix.rstrip("/")
    now = int(time.time())
    grant = ExecutionGrant(
        user_id=user.uid,
        team_id=str(team_id),
        agent_instance_id=agent_instance_id,
        action=ExecutionGrantAction.EXECUTE,
        audience=prefix,
        issued_at=now,
        expires_at=now + _EXECUTION_GRANT_TTL_SECONDS,
    )

    return ExecutionPreparation(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        runtime_id=source.runtime_id,
        execute_url=f"{prefix}/agents/execute",
        execute_stream_url=f"{prefix}/agents/execute/stream",
        messages_url_template=f"{prefix}/agents/sessions/{{session_id}}/messages",
        execution_grant=grant,
        expires_at=datetime.fromtimestamp(grant.expires_at, tz=timezone.utc),
        runtime_display_name=source.runtime_id,
    )


async def get_runtime_binding(
    agent_instance_id: str,
) -> ManagedAgentRuntimeBinding | None:
    """Resolve one managed agent instance into the runtime-facing binding payload."""
    store: AgentInstanceStore = (
        ApplicationContext.get_instance().get_agent_instance_store()
    )
    instance = await store.get(agent_instance_id)
    if instance is None:
        return None
    return ManagedAgentRuntimeBinding(
        agent_instance_id=instance.agent_instance_id,
        template_agent_id=instance.source_agent_id,
        owner_team_id=instance.team_id,
        enabled=instance.enabled,
        tuning=instance.tuning,
    )
