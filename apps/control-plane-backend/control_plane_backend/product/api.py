from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from fred_core import KeycloakUser, get_current_user, require_admin
from fred_core.common import TeamId

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    CreatePromptRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PromptDetail,
    PromptSummary,
    SessionListItem,
    UpdateAgentInstanceRequest,
    UpdatePromptRequest,
    UpdateSessionRequest,
)
from control_plane_backend.product.service import (
    EnrollmentError,
    ExecutionPreparationError,
    PromptRequestError,
    SessionAlreadyExistsError,
    build_frontend_bootstrap,
    create_session,
    create_prompt,
    delete_prompt,
    delete_session,
    enroll_agent_instance,
    get_prompt,
    get_runtime_binding,
    list_agent_templates,
    list_managed_agent_instances,
    list_prompts,
    list_sessions,
    prepare_execution,
    unenroll_agent_instance,
    update_agent_instance,
    update_prompt,
    update_session_activity,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)

router = APIRouter(tags=["Product"])
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.get(
    "/frontend/bootstrap",
    response_model=FrontendBootstrap,
    response_model_exclude_none=True,
    summary="Get the Phase 3a frontend bootstrap surface.",
)
async def get_frontend_bootstrap(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> FrontendBootstrap:
    """
    Return the typed frontend bootstrap payload owned by control-plane.

    Why this endpoint exists:
    - the frontend needs one small, control-plane-owned bootstrap surface for
      current user, team context, feature flags, and permissions

    How to use it:
    - call after user authentication during frontend startup

    Example:
    - `GET /control-plane/v1/frontend/bootstrap`
    """
    return await build_frontend_bootstrap(user, deps)


@router.get(
    "/teams/{team_id}/agent-templates",
    response_model=list[AgentTemplateSummary],
    response_model_exclude_none=True,
    summary="List instantiable agent templates for one team context.",
)
async def get_team_agent_templates(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[AgentTemplateSummary]:
    """
    Return the instantiable runtime templates visible from configured sources.

    Why this endpoint exists:
    - enrollment starts from live runtime catalogs, but the frontend should see
      one aggregated control-plane view

    How to use it:
    - call with one team id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/agent-templates`
    """
    del user
    return await list_agent_templates(team_id, deps)


@router.get(
    "/teams/{team_id}/agent-instances",
    response_model=list[ManagedAgentInstanceSummary],
    response_model_exclude_none=True,
    summary="List managed agent instances for one team.",
)
async def get_team_agent_instances(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[ManagedAgentInstanceSummary]:
    """
    Return the managed agent instances enrolled for one team.

    Why this endpoint exists:
    - the frontend needs a stable product list keyed by `agent_instance_id`,
      independent from runtime template availability

    How to use it:
    - call with one team id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/agent-instances`
    """
    del user
    return await list_managed_agent_instances(team_id, deps)


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
    deps: ProductDependencies,
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
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await enroll_agent_instance(
            user=user,
            team_id=team_id,
            request=body,
            deps=deps,
        )
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.patch(
    "/teams/{team_id}/agent-instances/{agent_instance_id}",
    response_model=ManagedAgentInstanceSummary,
    response_model_exclude_none=True,
    summary="Update display metadata or tuning field values for a managed agent instance.",
)
async def patch_team_agent_instance(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    body: UpdateAgentInstanceRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentInstanceSummary:
    """
    Update display_name, description, or tuning field values for one managed instance.

    Why this endpoint exists:
    - teams need to be able to customise an enrolled agent's display name,
      description, and per-instance field values without re-enrolling

    Policy — frozen snapshot:
    - field specs (ManagedAgentFieldSpec) are frozen at enrollment time and are
      never re-merged with the current template when the instance is edited
    - only field keys present in the instance's tuning.fields are considered;
      unknown keys are ignored for compatibility
    - known values are validated against the frozen field contract; invalid
      type/enum/range/pattern values return HTTP 422

    Returns 404 if the instance is not found for the given team.
    """
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        result = await update_agent_instance(
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            request=body,
            deps=deps,
        )
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent instance {agent_instance_id!r} not found for team {team_id!r}.",
        )
    return result


@router.delete(
    "/teams/{team_id}/agent-instances/{agent_instance_id}",
    status_code=204,
    response_model=None,
    summary="Unenroll (delete) a managed agent instance for a team.",
)
async def delete_team_agent_instance(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """
    Unenroll one managed agent instance for the given team.

    Why this endpoint exists:
    - Teams need to be able to remove agents they previously enrolled.

    Returns 404 if the instance is not found for the given team.
    """
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    deleted = await unenroll_agent_instance(
        team_id=team_id,
        agent_instance_id=agent_instance_id,
        deps=deps,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Agent instance {agent_instance_id!r} not found for team {team_id!r}.",
        )


@router.get(
    "/teams/{team_id}/prompts",
    response_model=list[PromptSummary],
    response_model_exclude_none=True,
    summary="List prompt-library records for one team.",
)
async def get_team_prompts(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[PromptSummary]:
    """
    Return the team-scoped prompt library for one team.

    Why this endpoint exists:
    - prompt management must be a first-class control-plane product surface,
      independent from managed-agent instance CRUD

    How to use it:
    - call with one team id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/prompts`
    """

    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    return await list_prompts(team_id, deps)


@router.post(
    "/teams/{team_id}/prompts",
    response_model=PromptSummary,
    response_model_exclude_none=True,
    status_code=201,
    summary="Create one team-scoped prompt-library record.",
)
async def post_team_prompt(
    team_id: Annotated[TeamId, Path()],
    body: CreatePromptRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Create one new prompt-library record for the given team.

    Why this endpoint exists:
    - prompt authoring and reuse should not require creating a managed agent
      instance first

    How to use it:
    - call with a team id plus `{ name, text, description? }`

    Example:
    - `POST /control-plane/v1/teams/personal/prompts`
    """

    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await create_prompt(user=user, team_id=team_id, request=body, deps=deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.get(
    "/teams/{team_id}/prompts/{prompt_id}",
    response_model=PromptDetail,
    response_model_exclude_none=True,
    summary="Get one team-scoped prompt-library record.",
)
async def get_team_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptDetail:
    """
    Return the full prompt-library record for one saved prompt.

    Why this endpoint exists:
    - prompt text inspection belongs to the control-plane product surface, not
      to managed-agent runtime bindings

    How to use it:
    - call with one team id and prompt id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/prompts/1234`
    """

    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    result = await get_prompt(team_id, prompt_id, deps)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


@router.put(
    "/teams/{team_id}/prompts/{prompt_id}",
    response_model=PromptSummary,
    response_model_exclude_none=True,
    summary="Replace one team-scoped prompt-library record.",
)
async def put_team_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    body: UpdatePromptRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Replace one saved prompt-library record for the given team.

    Why this endpoint exists:
    - prompt management starts with one intentionally simple mutable-record
      model before any future versioning or publication layers

    How to use it:
    - call with the full replacement `{ name, text, description? }`

    Example:
    - `PUT /control-plane/v1/teams/personal/prompts/1234`
    """

    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        result = await update_prompt(team_id, prompt_id, body, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


@router.delete(
    "/teams/{team_id}/prompts/{prompt_id}",
    status_code=204,
    response_model=None,
    summary="Delete one team-scoped prompt-library record.",
)
async def delete_team_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """
    Delete one saved prompt-library record for the given team.

    Why this endpoint exists:
    - prompt cleanup is a normal product operation and should stay available
      without entering the agent-creation flow

    How to use it:
    - call with a team id and prompt id after authentication

    Example:
    - `DELETE /control-plane/v1/teams/personal/prompts/1234`
    """

    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    deleted = await delete_prompt(team_id, prompt_id, deps)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )


@router.get(
    "/agent-instances/{agent_instance_id}/runtime",
    response_model=ManagedAgentRuntimeBinding,
    response_model_exclude_none=True,
    summary="Resolve one managed agent instance into its runtime binding (admin only).",
)
async def get_agent_instance_runtime(
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentRuntimeBinding:
    """
    Return the runtime-facing binding for one managed agent instance.

    Why this endpoint exists:
    - operators sometimes need to inspect the runtime identity behind one
      managed agent instance without exposing that binding broadly in the UI

    How to use it:
    - call as an admin with one `agent_instance_id`

    Example:
    - `GET /control-plane/v1/agent-instances/instance-1/runtime`
    """
    require_admin(user)
    binding = await get_runtime_binding(agent_instance_id, deps)
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
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> SessionListItem:
    """
    Create a control-plane session metadata record for a new conversation.

    Called by the frontend after generating a session_id (before or just after
    the first SSE turn). Does not affect runtime execution or history.

    Returns 409 if the session_id already exists.
    """
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await create_session(
            user=user,
            team_id=team_id,
            request=body,
            deps=deps,
        )
    except SessionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/teams/{team_id}/sessions",
    response_model=list[SessionListItem],
    response_model_exclude_none=True,
    summary="List session metadata for one team (sidebar use).",
)
async def get_team_sessions(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[SessionListItem]:
    """
    Return the most recent control-plane session metadata for one team.

    Why this endpoint exists:
    - the sidebar needs a lightweight team-scoped session list without loading
      runtime-owned message history

    How to use it:
    - call with one team id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/sessions`
    """
    del user
    return await list_sessions(team_id, deps=deps)


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
    deps: ProductDependencies,
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
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    updated = await update_session_activity(
        team_id=team_id,
        session_id=session_id,
        request=body,
        deps=deps,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id!r} not found for team {team_id!r}.",
        )
    return updated


@router.delete(
    "/teams/{team_id}/sessions/{session_id}",
    status_code=204,
    response_class=Response,
    summary="Delete session metadata for one team-scoped session.",
)
async def delete_team_session(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """
    Remove control-plane metadata for one team-scoped session.

    Returns 204 on success or when the session does not exist.
    Does not touch runtime-owned message history.
    """
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    await delete_session(team_id=team_id, session_id=session_id, deps=deps)
    return Response(status_code=204)


@router.post(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution",
    response_model=ExecutionPreparation,
    response_model_exclude_none=True,
    summary="Prepare one authorized runtime execution context for one managed agent instance.",
)
async def post_prepare_execution(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ExecutionPreparation:
    """
    Prepare an execution context for one team-scoped managed agent instance.

    Does not proxy runtime SSE, expose cluster-internal hostnames, or execute the agent.

    Returns an ExecutionPreparation with ingress-relative URLs and a short-lived
    ExecutionGrant scoped to the user/team/instance.
    """
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)

    try:
        return await prepare_execution(
            user=user,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            deps=deps,
        )
    except ExecutionPreparationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
