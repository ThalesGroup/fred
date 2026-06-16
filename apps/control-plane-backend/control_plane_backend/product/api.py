from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response
from fred_core import KeycloakUser, get_current_user, require_admin
from fred_core.common import TeamId
from fred_sdk.contracts.execution import ExecutionGrantAction

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    ContextPromptSummary,
    CreateAgentInstanceRequest,
    CreatePromptRequest,
    CreateSessionAttachmentRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    FrontendConfig,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PromptDetail,
    PromptPromoteRequest,
    PromptScoreUpdateRequest,
    PromptSummary,
    RuntimeAgentExecutionPreparation,
    SessionAttachmentSummary,
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
    SessionAttachmentRequestError,
    build_frontend_bootstrap,
    build_frontend_config,
    create_prompt,
    create_session,
    create_session_attachment,
    delete_prompt,
    delete_session,
    delete_session_attachment,
    enroll_agent_instance,
    get_prompt,
    get_runtime_binding,
    get_session,
    list_agent_templates,
    list_context_prompts,
    list_managed_agent_instances,
    list_prompts,
    list_session_attachments,
    list_sessions,
    prepare_execution,
    prepare_runtime_agent_execution,
    promote_prompt,
    record_prompt_use,
    unenroll_agent_instance,
    update_agent_instance,
    update_prompt,
    update_prompt_score,
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
    "/frontend/config",
    response_model=FrontendConfig,
    response_model_exclude_none=True,
    summary="Get the public pre-auth frontend configuration surface.",
)
async def get_frontend_config(deps: ProductDependencies) -> FrontendConfig:
    """
    Return the public (unauthenticated) pre-auth frontend config (FRONT-08).

    Why this endpoint exists:
    - the frontend must decide whether to initialize Keycloak BEFORE any login,
      so the auth decision cannot live on the authenticated `/frontend/bootstrap`
      surface (chicken-and-egg). The flag is derived from the backend
      `security.user` config, the single source of truth for user auth.

    How to use it:
    - call at Stage 0 of frontend startup, before the auth decision. No bearer
      token is required; only public OIDC client values are returned.

    Example:
    - `GET /control-plane/v1/frontend/config`
    """
    return build_frontend_config(deps)


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
    await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    return await list_managed_agent_instances(team.id, deps)


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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await enroll_agent_instance(
            user=user,
            team_id=team.id,
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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        result = await update_agent_instance(
            team_id=team.id,
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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    deleted = await unenroll_agent_instance(
        team_id=team.id,
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
    lang: str = "en",
) -> list[PromptSummary]:
    """
    Return the team-scoped prompt library merged with the 9 platform system defaults.

    Why this endpoint exists:
    - prompt management must be a first-class control-plane product surface,
      independent from managed-agent instance CRUD
    - system defaults are injected at query time so they are always present,
      always translated, and never lost regardless of user actions

    How to use it:
    - call with one team id and the UI language preference after authentication
    - pass ``lang=fr`` or ``lang=en`` (defaults to ``en``)

    Example:
    - `GET /control-plane/v1/teams/personal/prompts?lang=fr`
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    return await list_prompts(team.id, deps, lang=lang)


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

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await create_prompt(user=user, team_id=team.id, request=body, deps=deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.get(
    "/teams/{team_id}/prompts/context",
    response_model=list[ContextPromptSummary],
    summary="List personal + team prompts for the chat context picker.",
)
async def get_context_prompts_early(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    lang: str = Query(default="en"),
    user: KeycloakUser = Depends(get_current_user),
) -> list[ContextPromptSummary]:
    """
    Return the union of the calling user's personal prompts, the team's prompts,
    and the platform default prompts. DB prompts are ordered by session_count DESC;
    platform defaults are always appended after so that frequently-used custom prompts
    appear first.

    Registered before ``/prompts/{prompt_id}`` so FastAPI does not swallow
    the literal segment ``context`` as a path parameter.

    Example:
    - ``GET /control-plane/v1/teams/bid-and-capture/prompts/context?lang=fr``
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    return await list_context_prompts(user, team.id, deps, lang=lang)


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

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    result = await get_prompt(team.id, prompt_id, deps)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


@router.post(
    "/teams/{team_id}/prompts/{prompt_id}/use",
    response_class=Response,
    status_code=204,
    summary="Record one use of a prompt selected from any picker.",
)
async def post_record_prompt_use(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """
    Increment the session_count (or default_prompt_usage counter) for one prompt.

    Why this endpoint exists:
    - prompts can be selected from the chat context picker or from the agent-form
      prompt picker; both paths should contribute to the usage counter
    - the chat context picker fires this implicitly through PATCH /sessions,
      but the agent-form picker needs an explicit call

    How to use it:
    - fire-and-forget after the user confirms a prompt selection in any picker
    - works for both DB prompts (UUID ids) and default prompts ("default:<category>" ids)

    Example:
    - ``POST /control-plane/v1/teams/personal/prompts/default:doc-assist/use``
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    await record_prompt_use(prompt_id, team.id, user, deps)
    return Response(status_code=204)


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

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        result = await update_prompt(team.id, prompt_id, body, deps)
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

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    deleted = await delete_prompt(team.id, prompt_id, deps)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )


@router.post(
    "/teams/{team_id}/prompts/{prompt_id}/promote",
    response_model=PromptSummary,
    status_code=201,
    summary="Copy one prompt by value to a target team.",
)
async def post_promote_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    body: PromptPromoteRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Promote one team-scoped prompt to another team by copying its text and metadata.

    The source prompt is never modified. The new copy starts at version 1,
    import_count 0, session_count 0, score null.

    Returns 409 if a prompt with the same name already exists in the target team —
    the caller must rename first.

    Example:
    - ``POST /control-plane/v1/teams/personal/prompts/abc-123/promote``
      ``{ "target_team_id": "bid-and-capture" }``
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await promote_prompt(user, team.id, prompt_id, body, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.patch(
    "/teams/{team_id}/prompts/{prompt_id}",
    response_model=PromptSummary,
    summary="Update the quality score of one team-scoped prompt.",
)
async def patch_team_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    body: PromptScoreUpdateRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Set the explicit quality score (0.0–5.0) for one team-scoped prompt.

    Score is admin-settable. It will also be writable by the evaluation track (O1)
    once that harness is live. A null score is displayed as "-" in the UI.

    Example:
    - ``PATCH /control-plane/v1/teams/bid-and-capture/prompts/abc-123``
      ``{ "score": 4.5 }``
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    result = await update_prompt_score(team.id, prompt_id, body, deps)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await create_session(
            user=user,
            team_id=team.id,
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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    return await list_sessions(team.id, user_id=user.uid, deps=deps)


@router.get(
    "/teams/{team_id}/sessions/{session_id}",
    response_model=SessionListItem,
    response_model_exclude_none=True,
    summary="Fetch metadata for one team-scoped session.",
)
async def get_team_session(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> SessionListItem:
    """
    Return control-plane metadata for one session by ID, scoped to a team.

    Why this endpoint exists:
    - the chat header needs the session title without loading the full session list

    Returns 404 when the session does not exist for the given team.
    """
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    item = await get_session(team_id=team.id, session_id=session_id, deps=deps)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id!r} not found for team {team_id!r}.",
        )
    return item


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
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    updated = await update_session_activity(
        team_id=team.id,
        session_id=session_id,
        request=body,
        deps=deps,
        user=user,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id!r} not found for team {team_id!r}.",
        )
    return updated


@router.get(
    "/teams/{team_id}/sessions/{session_id}/attachments",
    response_model=list[SessionAttachmentSummary],
    response_model_exclude_none=True,
    summary="List persisted attachments for one team-scoped session.",
)
async def get_team_session_attachments(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[SessionAttachmentSummary]:
    """
    Return the persisted conversation-level attachments for one session.

    Why this endpoint exists:
    - the chat drawer needs reload-safe attachment state separate from the
      transient composer chips used for the current turn
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await list_session_attachments(
            team_id=team.id,
            session_id=session_id,
            user_id=user.uid,
            deps=deps,
        )
    except SessionAttachmentRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.post(
    "/teams/{team_id}/sessions/{session_id}/attachments",
    response_model=SessionAttachmentSummary,
    response_model_exclude_none=True,
    status_code=201,
    summary="Persist one attachment summary for a team-scoped session.",
)
async def post_team_session_attachment(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    body: CreateSessionAttachmentRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> SessionAttachmentSummary:
    """
    Persist one conversation attachment after successful upload and fast-ingest.
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await create_session_attachment(
            team_id=team.id,
            session_id=session_id,
            user_id=user.uid,
            request=body,
            deps=deps,
        )
    except SessionAttachmentRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.delete(
    "/teams/{team_id}/sessions/{session_id}/attachments/{attachment_id}",
    status_code=204,
    response_class=Response,
    summary="Delete one persisted session attachment and its Knowledge Flow artifacts.",
)
async def delete_team_session_attachment(
    request: Request,
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    attachment_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """
    Delete one persisted attachment for future turns.

    Existing chat history is left untouched; the deletion only affects future
    retrieval and future conversation context.
    """

    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        await delete_session_attachment(
            team_id=team.id,
            session_id=session_id,
            attachment_id=attachment_id,
            user_id=user.uid,
            authorization=request.headers.get("Authorization", ""),
            deps=deps,
        )
    except SessionAttachmentRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return Response(status_code=204)


@router.delete(
    "/teams/{team_id}/sessions/{session_id}",
    status_code=204,
    response_class=Response,
    summary="Delete session metadata for one team-scoped session.",
)
async def delete_team_session(
    team_id: Annotated[TeamId, Path()],
    session_id: Annotated[str, Path(min_length=1)],
    request: Request,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """
    Remove control-plane metadata for one team-scoped session.

    Returns 204 on success or when the session does not exist.
    Does not touch runtime-owned message history.
    """
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        await delete_session(
            team_id=team.id,
            session_id=session_id,
            user_id=user.uid,
            authorization=request.headers.get("Authorization", ""),
            deps=deps,
        )
    except SessionAttachmentRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post(
    "/teams/{team_id}/runtimes/{runtime_id}/agents/{agent_id}/prepare-execution",
    response_model=RuntimeAgentExecutionPreparation,
    response_model_exclude_none=True,
    summary="Prepare an execution grant for a direct runtime agent (evaluation use).",
)
async def post_prepare_runtime_agent_execution(
    team_id: Annotated[TeamId, Path()],
    runtime_id: Annotated[str, Path(min_length=1)],
    agent_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> RuntimeAgentExecutionPreparation:
    """
    Prepare an ingress-safe execution URL and short-lived grant for a direct
    runtime agent target. Used by the evaluation worker.
    """
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)
    try:
        return await prepare_runtime_agent_execution(
            user=user,
            team_id=team.id,
            runtime_id=runtime_id,
            agent_id=agent_id,
            deps=deps,
        )
    except ExecutionPreparationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


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
    session_id: str | None = None,
    action: ExecutionGrantAction = ExecutionGrantAction.EXECUTE,
) -> ExecutionPreparation:
    """
    Prepare an execution context for one team-scoped managed agent instance.

    Does not proxy runtime SSE, expose cluster-internal hostnames, or execute the agent.

    Returns an ExecutionPreparation with ingress-relative URLs and a short-lived
    ExecutionGrant scoped to the user/team/instance.

    Pass ``session_id`` (query param) to include ``context_prompt_text`` in the response
    when the session has a context prompt configured.

    Pass ``action=resume`` (query param) when the client intends to send a HITL resume
    payload — the grant will be issued with action=resume so the runtime accepts it.
    """
    team = await get_team_by_id_from_service(user, team_id, deps.team_dependencies)

    try:
        return await prepare_execution(
            user=user,
            team_id=team.id,
            agent_instance_id=agent_instance_id,
            session_id=session_id,
            action=action,
            deps=deps,
        )
    except ExecutionPreparationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
