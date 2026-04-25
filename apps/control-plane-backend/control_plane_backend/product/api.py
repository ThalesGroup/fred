from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fred_core import KeycloakUser, get_current_user, require_admin
from fred_core.common import TeamId

from control_plane_backend.product.service import (
    EnrollmentError,
    ExecutionPreparationError,
    build_frontend_bootstrap,
    create_session,
    enroll_agent_instance,
    get_runtime_binding,
    list_agent_templates,
    list_managed_agent_instances,
    list_sessions,
    prepare_execution,
    unenroll_agent_instance,
    update_session_activity,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    SessionListItem,
    UpdateSessionRequest,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)

router = APIRouter(tags=["Product"])


@router.get(
    "/frontend/bootstrap",
    response_model=FrontendBootstrap,
    response_model_exclude_none=True,
    summary="Get the Phase 3a frontend bootstrap surface.",
)
async def get_frontend_bootstrap(
    user: KeycloakUser = Depends(get_current_user),
) -> FrontendBootstrap:
    return await build_frontend_bootstrap(user)


@router.get(
    "/teams/{team_id}/agent-templates",
    response_model=list[AgentTemplateSummary],
    response_model_exclude_none=True,
    summary="List instantiable agent templates for one team context.",
)
async def get_team_agent_templates(
    team_id: Annotated[TeamId, Path()],
    user: KeycloakUser = Depends(get_current_user),
) -> list[AgentTemplateSummary]:
    del user
    return await list_agent_templates(team_id)


@router.get(
    "/teams/{team_id}/agent-instances",
    response_model=list[ManagedAgentInstanceSummary],
    response_model_exclude_none=True,
    summary="List managed agent instances for one team.",
)
async def get_team_agent_instances(
    team_id: Annotated[TeamId, Path()],
    user: KeycloakUser = Depends(get_current_user),
) -> list[ManagedAgentInstanceSummary]:
    del user
    return await list_managed_agent_instances(team_id)


@router.post(
    "/teams/{team_id}/agent-instances",
    response_model=ManagedAgentInstanceSummary,
    response_model_exclude_none=True,
    status_code=201,
    summary="Enroll a discovered template as a managed agent instance for a team.",
)
async def post_team_agent_instance(
    team_id: Annotated[TeamId, Path()],
    body: CreateAgentInstanceRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for the given team.

    Why this endpoint exists:
    - The frontend needs to create DB-backed managed instances from catalog templates
      before execution preparation (and therefore SSE execution) can work end-to-end.

    What this endpoint does:
    - Validates team membership via get_team_by_id (Keycloak + OpenFGA).
    - Derives source_runtime_id and source_agent_id from template_id.
    - Creates a new DB-backed ManagedAgentInstance record.
    - Returns the typed managed instance summary with the new agent_instance_id.

    Returns 404 if the template_id references an unknown or disabled runtime source.
    Returns 400 if template_id is malformed.
    """
    await get_team_by_id_from_service(user, team_id)
    try:
        return await enroll_agent_instance(user=user, team_id=team_id, request=body)
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.delete(
    "/teams/{team_id}/agent-instances/{agent_instance_id}",
    status_code=204,
    response_model=None,
    summary="Unenroll (delete) a managed agent instance for a team.",
)
async def delete_team_agent_instance(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """
    Unenroll one managed agent instance for the given team.

    Why this endpoint exists:
    - Teams need to be able to remove agents they previously enrolled.

    Returns 404 if the instance is not found for the given team.
    """
    await get_team_by_id_from_service(user, team_id)
    deleted = await unenroll_agent_instance(
        team_id=team_id, agent_instance_id=agent_instance_id
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Agent instance {agent_instance_id!r} not found for team {team_id!r}.",
        )


@router.get(
    "/agent-instances/{agent_instance_id}/runtime",
    response_model=ManagedAgentRuntimeBinding,
    response_model_exclude_none=True,
    summary="Resolve one managed agent instance into its runtime binding (admin only).",
)
async def get_agent_instance_runtime(
    agent_instance_id: Annotated[str, Path(min_length=1)],
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentRuntimeBinding:
    require_admin(user)
    binding = await get_runtime_binding(agent_instance_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Unknown agent instance.")
    if not binding.enabled:
        raise HTTPException(
            status_code=409, detail="Managed agent instance is disabled."
        )
    return binding


@router.post(
    "/teams/{team_id}/sessions",
    response_model=SessionListItem,
    response_model_exclude_none=True,
    status_code=201,
    summary="Register session metadata in control-plane at session creation time.",
)
async def post_team_session(
    team_id: Annotated[TeamId, Path()],
    body: CreateSessionRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> SessionListItem:
    """
    Create a control-plane session metadata record for a new conversation.

    Called by the frontend after generating a session_id (before or just after
    the first SSE turn). Does not affect runtime execution or history.

    Returns 409 if the session_id already exists.
    """
    await get_team_by_id_from_service(user, team_id)
    try:
        return await create_session(user=user, team_id=team_id, request=body)
    except Exception as exc:
        if "UNIQUE constraint" in str(exc) or "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Session {body.session_id!r} already exists.",
            ) from exc
        raise


@router.get(
    "/teams/{team_id}/sessions",
    response_model=list[SessionListItem],
    response_model_exclude_none=True,
    summary="List session metadata for one team (sidebar use).",
)
async def get_team_sessions(
    team_id: Annotated[TeamId, Path()],
    user: KeycloakUser = Depends(get_current_user),
) -> list[SessionListItem]:
    """Return the most recent sessions for this team, newest first."""
    del user
    return await list_sessions(team_id)


@router.patch(
    "/teams/{team_id}/sessions/{session_id}",
    response_model=SessionListItem,
    response_model_exclude_none=True,
    summary="Refresh session metadata after a managed turn.",
)
async def patch_team_session(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    body: UpdateSessionRequest,
    user: KeycloakUser = Depends(get_current_user),
) -> SessionListItem:
    """
    Update control-plane-owned metadata for one team-scoped session.

    Why this endpoint exists:
    - The sidebar is sorted from control-plane session metadata, but runtime
      remains the owner of message history and the hot execution path.

    How to use it:
    - after a managed turn completes, PATCH `{ "updated_at": "<ISO datetime>" }`
      for the active team/session.

    Returns 404 if the session does not exist for the given team.
    """
    await get_team_by_id_from_service(user, team_id)
    updated = await update_session_activity(
        team_id=team_id,
        session_id=session_id,
        request=body,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id!r} not found for team {team_id!r}.",
        )
    return updated


@router.post(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution",
    response_model=ExecutionPreparation,
    response_model_exclude_none=True,
    summary="Prepare one authorized runtime execution context for one managed agent instance.",
)
async def post_prepare_execution(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    user: KeycloakUser = Depends(get_current_user),
) -> ExecutionPreparation:
    """
    Prepare an execution context for one team-scoped managed agent instance.

    Does not proxy runtime SSE, expose cluster-internal hostnames, or execute the agent.

    Returns an ExecutionPreparation with ingress-relative URLs and a short-lived
    ExecutionGrant scoped to the user/team/instance.
    """
    await get_team_by_id_from_service(user, team_id)

    try:
        return await prepare_execution(
            user=user,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
        )
    except ExecutionPreparationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
