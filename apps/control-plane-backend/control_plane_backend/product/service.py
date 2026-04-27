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

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PermissionSummary,
    SessionListItem,
    UpdateAgentInstanceRequest,
    UpdateSessionRequest,
)
from control_plane_backend.sessions.store import (
    SessionMetadataAlreadyExistsError,
    SessionMetadataRecord,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams.service import list_teams as list_teams_from_service
from control_plane_backend.users.schemas import UserSummary

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
        default_tuning: ManagedAgentTuning | None = None,
    ) -> None:
        self.template_agent_id = template_agent_id
        self.title = title
        self.description = description
        self.kind = kind
        self.default_tuning = default_tuning or ManagedAgentTuning(
            role=title,
            description=description,
        )

    @classmethod
    def model_validate(cls, data: dict) -> "_RuntimeTemplatePayload":
        return cls(
            template_agent_id=data["template_agent_id"],
            title=data["title"],
            description=data["description"],
            kind=data["kind"],
            default_tuning=ManagedAgentTuning.model_validate(
                data.get("default_tuning")
                or {
                    "role": data["title"],
                    "description": data["description"],
                }
            ),
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


async def build_frontend_bootstrap(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> FrontendBootstrap:
    """Build the frontend bootstrap from the shared selectable-team services.

    Why this function exists:
    - bootstrap should consume the same team resolution contract as `/teams` and
      `/teams/{team_id}` so `personal` is not shaped differently per endpoint

    How to use it:
    - call from the frontend bootstrap controller after authentication

    Example:
    - `payload = await build_frontend_bootstrap(user, deps)`
    """
    active_team, available_teams = await asyncio.gather(
        get_team_by_id_from_service(
            user,
            PERSONAL_TEAM_ID,
            deps.team_dependencies,
        ),
        list_teams_from_service(user, deps.team_dependencies),
    )
    return FrontendBootstrap(
        current_user=UserSummary.from_keycloak_user(user),
        active_team=active_team,
        available_teams=available_teams,
        gcu_version=deps.configuration.app.gcu_version,
        feature_flags=deps.configuration.platform.frontend.feature_flags,
        ui_settings=deps.configuration.platform.frontend.ui_settings,
        permissions=_build_permission_summary(user),
    )


async def _fetch_runtime_templates(base_url: str) -> list[_RuntimeTemplatePayload]:
    url = f"{base_url.rstrip('/')}/agents/templates"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    return [_RuntimeTemplatePayload.model_validate(item) for item in payload]


async def list_agent_templates(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> list[AgentTemplateSummary]:
    """
    Aggregate template summaries from all enabled configured runtime pods.

    Why this function exists:
    - template discovery is a control-plane product concern that must merge the
      live catalogs exposed by configured runtime pods

    How to use it:
    - call from the team template-listing route for one team context
    - pass request-scoped product dependencies when available

    Example:
    - `templates = await list_agent_templates(team_id, deps)`
    """
    templates: list[AgentTemplateSummary] = []
    for source in deps.configuration.platform.runtime_catalog_sources:
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
                    default_tuning_fields=template.default_tuning.fields,
                )
            )
    return templates


async def list_managed_agent_instances(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> list[ManagedAgentInstanceSummary]:
    """
    Return the enrolled managed agent instances for one team from the DB.

    Why this function exists:
    - the product surface must expose managed agent instances by stable
      `agent_instance_id`, separate from live runtime catalog discovery

    How to use it:
    - call from the team agent-instances route
    - pass request-scoped product dependencies when available

    Example:
    - `instances = await list_managed_agent_instances(team_id, deps)`
    """
    store = deps.get_agent_instance_store()
    records = await store.list_by_team(team_id)
    return [_record_to_summary(record) for record in records]


def _record_to_summary(record: AgentInstanceRecord) -> ManagedAgentInstanceSummary:
    """Build a frontend-facing summary from a DB-backed agent instance record."""
    return ManagedAgentInstanceSummary(
        agent_instance_id=record.agent_instance_id,
        team_id=record.team_id,
        template_id=record.template_id,
        display_name=record.display_name,
        description=record.description,
        status="enabled" if record.enabled else "disabled",
        created_at=record.created_at,
        updated_at=record.updated_at,
        created_by=record.created_by,
        tuning_field_values=record.tuning.values,
    )


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


class SessionAlreadyExistsError(Exception):
    """Raised when control-plane session metadata already exists."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id!r} already exists.")
        self.session_id = session_id


async def enroll_agent_instance(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateAgentInstanceRequest,
    deps: ProductServiceDependencies,
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for a team, creating a DB-backed managed instance.

    Why this function exists:
    - enrollment turns one live template into a DB-backed managed instance that
      can later be prepared for team-scoped execution

    How to use it:
    - pass a validated team, the authenticated user, and the typed enrollment
      request
    - pass request-scoped product dependencies when available

    Example:
    - `item = await enroll_agent_instance(user=user, team_id=team_id, request=body, deps=deps)`
    """
    parts = request.template_id.split(":", 1)
    if len(parts) != 2:
        raise EnrollmentError(
            f"Invalid template_id {request.template_id!r}. "
            "Expected format: '{source_runtime_id}:{source_agent_id}'."
        )
    source_runtime_id, source_agent_id = parts

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
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
    runtime_templates = await _fetch_runtime_templates(source.base_url)
    template = next(
        (
            item
            for item in runtime_templates
            if item.template_agent_id == source_agent_id
        ),
        None,
    )
    if template is None:
        raise EnrollmentError(
            f"Template {request.template_id!r} was not found on runtime source "
            f"{source_runtime_id!r}.",
            http_status=404,
        )

    tuning = template.default_tuning.model_copy(
        update={
            "role": request.display_name,
            "description": request.description or request.display_name,
        }
    )
    if request.tuning_field_values:
        valid_keys = {f.key for f in tuning.fields}
        tuning = tuning.model_copy(
            update={
                "values": {
                    k: v
                    for k, v in request.tuning_field_values.items()
                    if k in valid_keys
                }
            }
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

    store = deps.get_agent_instance_store()
    created = await store.create(record)
    return _record_to_summary(created)


async def update_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    request: UpdateAgentInstanceRequest,
    deps: ProductServiceDependencies,
) -> ManagedAgentInstanceSummary | None:
    """
    Update display_name, description, or tuning field values for one managed instance.

    Why this function exists:
    - teams need to be able to customise display metadata and per-instance field
      values after enrollment without re-enrolling from scratch

    How to use it:
    - pass only the fields to change; None fields are left unchanged
    - tuning_field_values replaces the stored values dict entirely (filtered to
      known keys); pass None to leave existing values untouched

    Policy — frozen snapshot:
    - field specs (ManagedAgentFieldSpec) are frozen at enrollment time
    - they are never re-merged with the current template when the instance is edited
    - only known keys (present in instance.tuning.fields) are accepted

    Example:
    - `result = await update_agent_instance(team_id=team_id, agent_instance_id=id, request=req, deps=deps)`
    """
    store = deps.get_agent_instance_store()
    record = await store.get_for_team(agent_instance_id, team_id)
    if record is None:
        return None

    new_tuning: ManagedAgentTuning | None = None
    if request.tuning_field_values is not None:
        valid_keys = {f.key for f in record.tuning.fields}
        new_tuning = record.tuning.model_copy(
            update={
                "values": {
                    k: v
                    for k, v in request.tuning_field_values.items()
                    if k in valid_keys
                }
            }
        )

    updated = await store.update(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        display_name=request.display_name,
        description=request.description,
        tuning=new_tuning,
    )
    return _record_to_summary(updated) if updated is not None else None


async def unenroll_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Unenroll (delete) one managed agent instance for a team.

    Why this function exists:
    - managed agent lifecycle stays in control-plane, so unbinding is a local
      metadata deletion rather than a runtime call

    How to use it:
    - call after team authorization has already been checked
    - pass request-scoped product dependencies when available

    Example:
    - `deleted = await unenroll_agent_instance(team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()
    return await store.delete(agent_instance_id, team_id)


async def prepare_execution(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> ExecutionPreparation:
    """
    Prepare one authorized runtime execution context for one managed agent instance.

    Why this function exists:
    - control-plane must issue team-scoped execution context and ingress-safe
      runtime URLs without taking over runtime execution itself

    How to use it:
    - call after team membership has already been validated
    - pass request-scoped product dependencies when available

    Example:
    - `prep = await prepare_execution(user=user, team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()

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
            for s in deps.configuration.platform.runtime_catalog_sources
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
    deps: ProductServiceDependencies,
) -> ManagedAgentRuntimeBinding | None:
    """
    Resolve one managed agent instance into the runtime-facing binding payload.

    Why this function exists:
    - operators and internal flows need a typed way to inspect how one managed
      instance maps back to its runtime-facing identity

    How to use it:
    - call with one `agent_instance_id`
    - pass request-scoped product dependencies when available

    Example:
    - `binding = await get_runtime_binding("inst-1", deps)`
    """
    store = deps.get_agent_instance_store()
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


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


async def create_session(
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateSessionRequest,
    deps: ProductServiceDependencies,
) -> SessionListItem:
    """
    Register one new control-plane-owned session metadata record.

    Why this function exists:
    - the frontend needs a lightweight control-plane row as soon as a team
      session starts, before later activity refreshes
    - duplicate `session_id` creation should surface as a domain conflict
      rather than a storage-specific exception

    How to use it:
    - call once when a team starts a brand-new session id
    - catch `SessionAlreadyExistsError` when a duplicate should map to HTTP 409

    Example:
    - `item = await create_session(user, team_id, request, deps)`
    """
    record = SessionMetadataRecord(
        session_id=request.session_id,
        team_id=team_id,
        agent_instance_id=request.agent_instance_id,
        user_id=user.username if user else None,
        title=request.title,
    )
    try:
        created = await deps.get_session_metadata_store().create(record)
    except SessionMetadataAlreadyExistsError as exc:
        raise SessionAlreadyExistsError(request.session_id) from exc
    return _record_to_item(created)


async def list_sessions(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    limit: int = 50,
) -> list[SessionListItem]:
    """
    List session metadata records for one team, newest first.

    Why this function exists:
    - the frontend sidebar needs a lightweight control-plane list, separate from
      runtime-owned message history

    How to use it:
    - call from the team sessions route
    - pass request-scoped product dependencies when available

    Example:
    - `sessions = await list_sessions(team_id, limit=50, deps=deps)`
    """
    records = await deps.get_session_metadata_store().list_by_team(
        team_id,
        limit=limit,
    )
    return [_record_to_item(r) for r in records]


async def update_session_activity(
    team_id: TeamId,
    session_id: str,
    request: UpdateSessionRequest,
    deps: ProductServiceDependencies,
) -> SessionListItem | None:
    """
    Refresh control-plane metadata for one completed managed turn.

    Why this function exists:
    - The sidebar sorts sessions by control-plane-owned `updated_at`, while
      runtime remains the only owner of message content.

    How to use it:
    - call from the PATCH session metadata endpoint after runtime reports a
      completed turn.

    Example:
    - `await update_session_activity(team_id, session_id, request, deps)`
    """
    record = await deps.get_session_metadata_store().update_last_activity(
        session_id=session_id,
        team_id=team_id,
        updated_at=request.updated_at,
    )
    if record is None:
        return None
    return _record_to_item(record)


def _record_to_item(record: SessionMetadataRecord) -> SessionListItem:
    return SessionListItem(
        session_id=record.session_id,
        team_id=record.team_id,
        agent_instance_id=record.agent_instance_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
