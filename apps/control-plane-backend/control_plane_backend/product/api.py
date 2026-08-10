from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
    get_current_user,
)
from fred_core.common import TeamId
from fred_core.kpi import runtime_stage_timer
from pydantic import ValidationError

from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    ContextPromptSummary,
    CreateAgentInstanceRequest,
    CreatePromptCategoryRequest,
    CreatePromptRequest,
    CreateSessionAttachmentRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    FrontendConfig,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    MarketplaceImportRequest,
    MarketplaceImportResponse,
    MarketplaceImportResult,
    MarketplacePromptSummary,
    PromptCategorySummary,
    PromptDetail,
    PromptPromoteRequest,
    PromptScoreUpdateRequest,
    PromptSummary,
    RuntimeAgentExecutionPreparation,
    SessionAttachmentSummary,
    SessionListItem,
    UpdateAgentInstanceRequest,
    UpdatePromptCategoryRequest,
    UpdatePromptRequest,
    UpdateSessionRequest,
)
from control_plane_backend.product.service import (
    CapabilityAssetFile,
    EnrollmentError,
    ExecutionPreparationError,
    PromptRequestError,
    SessionAlreadyExistsError,
    SessionAttachmentRequestError,
    build_frontend_bootstrap,
    build_frontend_config,
    create_prompt,
    create_prompt_category,
    create_session,
    create_session_attachment,
    delete_or_defer_session,
    delete_prompt,
    delete_prompt_category,
    delete_session_attachment,
    enroll_agent_instance,
    get_prompt,
    get_runtime_binding_for_team,
    get_session,
    import_published_prompt_into_team,
    list_agent_templates,
    list_context_prompts,
    list_managed_agent_instances,
    list_marketplace_prompts,
    list_prompt_categories,
    list_prompts,
    list_session_attachments,
    list_sessions,
    prepare_execution,
    prepare_runtime_agent_execution,
    promote_prompt,
    record_marketplace_prompt_use,
    record_prompt_use,
    set_prompt_published,
    unenroll_agent_instance,
    update_agent_instance,
    update_prompt,
    update_prompt_category,
    update_prompt_score,
    update_session_activity,
)
from control_plane_backend.teams.service import require_team_access

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
    Return the public (unauthenticated) pre-auth frontend config.

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
    return await build_frontend_config(deps)


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
    include_non_public: bool = False,
) -> list[AgentTemplateSummary]:
    """
    Return the instantiable runtime templates visible from configured sources.

    Why this endpoint exists:
    - enrollment starts from live runtime catalogs, but the frontend should see
      one aggregated control-plane view

    How to use it:
    - call with one team id after authentication
    - pass `include_non_public=true` to also list internal agents
      (`AgentDefinition.public=False`); the default catalog hides them so they
      do not appear in "create agent" (see AGENT-VISIBILITY-RFC)

    Internal agents are an admin concern: `include_non_public` is honored only for
    OpenFGA `platform_admin`/`platform_observer` subjects (checked via
    `CAN_MANAGE_PLATFORM`) and silently ignored for everyone else, so a non-admin
    team member cannot enumerate hidden agents, and a Keycloak `admin` role alone
    is no longer sufficient.

    Example:
    - `GET /control-plane/v1/teams/personal/agent-templates`
    """
    await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
    rebac = deps.team_dependencies.rebac
    effective_include_non_public = (
        include_non_public
        and await rebac.has_user_permission(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )
    )
    return await list_agent_templates(
        team_id, deps, include_non_public=effective_include_non_public
    )


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
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
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
    http_request: Request,
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for the given team.

    Why this endpoint exists:
    - The frontend needs to create DB-backed managed instances from catalog templates
      before execution preparation (and therefore SSE execution) can work end-to-end.

    What this endpoint does:
    - Validates team access via require_team_access (ReBAC/OpenFGA — Keycloak
      only authenticates the caller, it is never the team-authorization source).
    - Derives source_runtime_id and source_agent_id from template_id.
    - Creates a new DB-backed ManagedAgentInstance record.
    - Returns the typed managed instance summary with the new agent_instance_id.

    Returns 404 if the template_id references an unknown or disabled runtime source.
    Returns 400 if template_id is malformed.
    """
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    try:
        return await enroll_agent_instance(
            user=user,
            team_id=team_id,
            request=body,
            deps=deps,
            # Forwarded to the pod's capability validate-config round-trip
            # (#1974) so pod-side auth sees the acting user.
            authorization=http_request.headers.get("Authorization"),
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
    http_request: Request,
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
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    try:
        result = await update_agent_instance(
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            request=body,
            deps=deps,
            user=user,
            authorization=http_request.headers.get("Authorization"),
        )
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent instance {agent_instance_id!r} not found for team {team_id!r}.",
        )
    return result


async def _parse_capability_asset_uploads(
    asset_slots: list[str],
    asset_files: list[UploadFile],
) -> dict[str, list[CapabilityAssetFile]]:
    """
    Pair the parallel `asset_slots` / `asset_files` multipart arrays (#1903).

    Each slot entry is `{capability_id}:{slot_key}` and addresses the file at
    the same index. Control-plane never opens the bytes — the pod's declared
    `AssetSlot` gate (cardinality, extension) and the capability's own content
    validation both run pod-side on the relayed multipart.
    """
    if len(asset_slots) != len(asset_files):
        raise HTTPException(
            status_code=422,
            detail=(
                "asset_slots and asset_files must have the same length "
                f"(got {len(asset_slots)} slots for {len(asset_files)} files)."
            ),
        )
    uploads: dict[str, list[CapabilityAssetFile]] = {}
    for slot_ref, upload in zip(asset_slots, asset_files):
        capability_id, separator, slot_key = slot_ref.partition(":")
        if not separator or not capability_id or not slot_key:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid asset slot reference {slot_ref!r}; expected "
                    "'{capability_id}:{slot_key}'."
                ),
            )
        uploads.setdefault(capability_id, []).append(
            CapabilityAssetFile(
                slot_key=slot_key,
                filename=upload.filename or slot_key,
                content=await upload.read(),
                content_type=upload.content_type,
            )
        )
    return uploads


@router.post(
    "/teams/{team_id}/agent-instances/with-assets",
    response_model=ManagedAgentInstanceSummary,
    response_model_exclude_none=True,
    status_code=201,
    summary=(
        "Enroll a template as a managed agent instance with capability asset "
        "uploads (multipart)."
    ),
)
async def post_team_agent_instance_with_assets(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    http_request: Request,
    request: Annotated[
        str, Form(description="CreateAgentInstanceRequest as a JSON object string")
    ],
    asset_slots: Annotated[
        list[str],
        Form(
            description=(
                "One '{capability_id}:{slot_key}' reference per uploaded file, "
                "aligned by index with asset_files."
            )
        ),
    ] = [],
    asset_files: Annotated[list[UploadFile], File()] = [],
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentInstanceSummary:
    """
    Multipart companion of `POST /teams/{team_id}/agent-instances` (#1903,
    AGENT-CAPABILITY-RFC §3.4).

    Why this endpoint exists:
    - an asset-bearing capability (e.g. `ppt_filler`) needs its uploaded file to
      travel INSIDE the atomic agent save, so the pod's `validate_config` can
      parse it, store the binary, and persist the derived config in one step —
      control-plane is a pure relay and never opens the bytes
    - the JSON route stays unchanged for every save that carries no upload
    """
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    try:
        body = CreateAgentInstanceRequest.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    uploads = await _parse_capability_asset_uploads(asset_slots, asset_files)
    try:
        return await enroll_agent_instance(
            user=user,
            team_id=team_id,
            request=body,
            deps=deps,
            authorization=http_request.headers.get("Authorization"),
            asset_uploads=uploads,
        )
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.patch(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/with-assets",
    response_model=ManagedAgentInstanceSummary,
    response_model_exclude_none=True,
    summary=(
        "Update a managed agent instance with capability asset uploads (multipart)."
    ),
)
async def patch_team_agent_instance_with_assets(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    http_request: Request,
    request: Annotated[
        str, Form(description="UpdateAgentInstanceRequest as a JSON object string")
    ],
    asset_slots: Annotated[
        list[str],
        Form(
            description=(
                "One '{capability_id}:{slot_key}' reference per uploaded file, "
                "aligned by index with asset_files."
            )
        ),
    ] = [],
    asset_files: Annotated[list[UploadFile], File()] = [],
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentInstanceSummary:
    """
    Multipart companion of `PATCH /teams/{team_id}/agent-instances/{id}` (#1903)
    — same relay semantics as the enroll variant; see it for the rationale.
    """
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    try:
        body = UpdateAgentInstanceRequest.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    uploads = await _parse_capability_asset_uploads(asset_slots, asset_files)
    try:
        result = await update_agent_instance(
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            request=body,
            deps=deps,
            user=user,
            authorization=http_request.headers.get("Authorization"),
            asset_uploads=uploads,
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
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
    )
    deleted = await unenroll_agent_instance(
        team_id=team_id,
        agent_instance_id=agent_instance_id,
        deps=deps,
        user=user,
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
    Return the team-scoped prompt library.

    Why this endpoint exists:
    - prompt management must be a first-class control-plane product surface,
      independent from managed-agent instance CRUD
    - every prompt is a real, editable team row (PROMPT-09) — new teams start
      with a starter kit seeded at creation, not a read-only platform catalog

    How to use it:
    - call with one team id after authentication

    Example:
    - `GET /control-plane/v1/teams/personal/prompts`
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
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

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        return await create_prompt(user=user, team_id=team_id, request=body, deps=deps)
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
    user: KeycloakUser = Depends(get_current_user),
) -> list[ContextPromptSummary]:
    """
    Return the calling user's personal prompts (personal space) or the team's
    prompts (team space) for the chat-context picker, ordered by session_count
    DESC (most-used first).

    Registered before ``/prompts/{prompt_id}`` so FastAPI does not swallow
    the literal segment ``context`` as a path parameter.

    Example:
    - ``GET /control-plane/v1/teams/bid-and-capture/prompts/context``
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
    return await list_context_prompts(user, team_id, deps)


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

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
    result = await get_prompt(team_id, prompt_id, deps)
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
    Increment the session_count for one prompt.

    Why this endpoint exists:
    - prompts can be selected from the chat context picker or from the agent-form
      prompt picker; both paths should contribute to the usage counter
    - the chat context picker fires this implicitly through PATCH /sessions,
      but the agent-form picker needs an explicit call

    How to use it:
    - fire-and-forget after the user confirms a prompt selection in any picker

    AUTHZ-05 post-implementation review finding: this write (it increments a
    persistent counter) used to fall back to the default `CAN_READ`, which
    also admits `public` — any authenticated user who could merely view a
    public team, without being a member, could repeatedly call this to skew
    the "most-used" prompt ranking. Gated on `CAN_USE_TEAM_AGENTS` instead —
    the existing team_member-only (excludes `public`) capability already used
    for the sibling agent-template/agent-instance listing endpoints; prompt
    selection happens from the same chat/agent-form pickers this capability
    already gates, so no new capability is introduced for this one call site.

    Example:
    - ``POST /control-plane/v1/teams/personal/prompts/abc-123/use``
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
    await record_prompt_use(prompt_id, team_id, user, deps)
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

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
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

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    deleted = await delete_prompt(team_id, prompt_id, deps)
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

    AUTHZ-05 post-implementation review finding (2026-07-11): promoting only
    checked `CAN_UPDATE_RESOURCES` on the source team. The target team was never
    resolved or permission-checked, so any team_editor could copy a prompt's
    text into an arbitrary team_id — including teams they hold no relation to —
    as long as the name didn't collide there. Resolving the target team here,
    under the same `CAN_UPDATE_RESOURCES` requirement as the source, closes that
    cross-team write and also turns an unknown target into a 404 instead of a
    silent orphan row.

    Example:
    - ``POST /control-plane/v1/teams/personal/prompts/abc-123/promote``
      ``{ "target_team_id": "bid-and-capture" }``
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    await require_team_access(
        user,
        TeamId(body.target_team_id),
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        return await promote_prompt(user, team_id, prompt_id, body, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.post(
    "/teams/{team_id}/prompts/{prompt_id}/publish",
    response_model=PromptSummary,
    response_model_exclude_none=True,
    summary="Publish one team prompt to the global marketplace.",
)
async def post_publish_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Publish one team prompt to the "Prompts de la communauté" marketplace.

    Publishing is a live visibility flag on the team's own row (PROMPT-06): the
    marketplace shows this same record, so edits and the shared usage counter
    propagate immediately. Only team editors of the author team may publish, and
    only real team prompts are publishable (personal-space prompts stay private,
    rejected with 400).

    Example:
    - ``POST /control-plane/v1/teams/bid-and-capture/prompts/abc-123/publish``
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        result = await set_prompt_published(team_id, prompt_id, True, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


@router.post(
    "/teams/{team_id}/prompts/{prompt_id}/unpublish",
    response_model=PromptSummary,
    response_model_exclude_none=True,
    summary="Remove one team prompt from the global marketplace.",
)
async def post_unpublish_prompt(
    team_id: Annotated[TeamId, Path()],
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptSummary:
    """
    Withdraw one team prompt from the marketplace.

    Only team editors of the author team may unpublish. After this call the
    prompt is no longer discoverable, usable, or importable by other users; the
    team keeps its own private copy unchanged.

    Example:
    - ``POST /control-plane/v1/teams/bid-and-capture/prompts/abc-123/unpublish``
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        result = await set_prompt_published(team_id, prompt_id, False, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


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

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    result = await update_prompt_score(team_id, prompt_id, body, deps)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {prompt_id!r} not found for team {team_id!r}.",
        )
    return result


# ---------------------------------------------------------------------------
# Prompts marketplace (PROMPT-06) — cross-team discovery / use / import
# ---------------------------------------------------------------------------


@router.get(
    "/marketplace/prompts",
    response_model=list[MarketplacePromptSummary],
    response_model_exclude_none=True,
    summary="List every published prompt in the global marketplace.",
)
async def get_marketplace_prompts(
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[MarketplacePromptSummary]:
    """
    Return all published prompts ("Prompts de la communauté"), most-used first.

    Not team-scoped: any authenticated user may browse the community marketplace
    regardless of team membership. Each entry carries the author team's display
    name, used as the card label and the team filter chip.

    Example:
    - ``GET /control-plane/v1/marketplace/prompts``
    """

    return await list_marketplace_prompts(deps)


@router.post(
    "/marketplace/prompts/{prompt_id}/use",
    response_class=Response,
    status_code=204,
    summary="Record one use of a published marketplace prompt.",
)
async def post_marketplace_prompt_use(
    prompt_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> Response:
    """
    Increment the shared usage counter when a user copies a marketplace prompt.

    The counter reflects total, global usage across the whole application, so
    any authenticated user's copy counts — team membership is not required.
    Only published prompts are counted; an unpublished/unknown id is 404.

    Example:
    - ``POST /control-plane/v1/marketplace/prompts/abc-123/use``
    """

    recorded = await record_marketplace_prompt_use(prompt_id, deps)
    if not recorded:
        raise HTTPException(
            status_code=404,
            detail=f"Published prompt {prompt_id!r} not found in the marketplace.",
        )
    return Response(status_code=204)


@router.post(
    "/marketplace/prompts/{prompt_id}/import",
    response_model=MarketplaceImportResponse,
    summary="Import a published prompt into one or more teams.",
)
async def post_marketplace_prompt_import(
    prompt_id: Annotated[str, Path(min_length=1)],
    body: MarketplaceImportRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceImportResponse:
    """
    Copy one published prompt (by value) into every selected target space.

    Each target is authorized independently: the caller must be an editor of
    the target space (personal space or a team where they hold `team_editor`).
    A target the caller cannot edit, or an unknown team, yields a per-target
    error rather than failing the whole request. Each successful copy is a fresh
    instance with a reset counter and a ``_imported-N`` name.

    Example:
    - ``POST /control-plane/v1/marketplace/prompts/abc-123/import``
      ``{ "target_team_ids": ["personal", "bid-and-capture"] }``
    """

    results: list[MarketplaceImportResult] = []
    for raw_team_id in body.target_team_ids:
        try:
            target_team_id = await require_team_access(
                user,
                TeamId(raw_team_id),
                deps.team_dependencies,
                required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
            )
        except HTTPException as exc:
            results.append(
                MarketplaceImportResult(team_id=raw_team_id, error=str(exc.detail))
            )
            continue
        try:
            summary = await import_published_prompt_into_team(
                user, prompt_id, target_team_id, deps
            )
            results.append(
                MarketplaceImportResult(team_id=str(target_team_id), prompt=summary)
            )
        except PromptRequestError as exc:
            results.append(
                MarketplaceImportResult(team_id=str(target_team_id), error=str(exc))
            )
    return MarketplaceImportResponse(results=results)


@router.get(
    "/teams/{team_id}/prompt-categories",
    response_model=list[PromptCategorySummary],
    summary="List one team's prompt categories.",
)
async def get_team_prompt_categories(
    team_id: Annotated[TeamId, Path()],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[PromptCategorySummary]:
    """
    List one team's prompt categories, alphabetically.

    Why this endpoint exists (PROMPT-09):
    - categories are team-owned content, not a platform-wide taxonomy — every
      team manages its own set, starting from a starter kit seeded at creation

    Example:
    - `GET /control-plane/v1/teams/bid-and-capture/prompt-categories`
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )
    return await list_prompt_categories(team_id, deps)


@router.post(
    "/teams/{team_id}/prompt-categories",
    response_model=PromptCategorySummary,
    status_code=201,
    summary="Create one team-scoped prompt category.",
)
async def post_team_prompt_category(
    team_id: Annotated[TeamId, Path()],
    body: CreatePromptCategoryRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptCategorySummary:
    """
    Create one new prompt category for the given team.

    Example:
    - `POST /control-plane/v1/teams/bid-and-capture/prompt-categories`
      `{ "name": "Support client" }`
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        return await create_prompt_category(team_id, body, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.put(
    "/teams/{team_id}/prompt-categories/{category_id}",
    response_model=PromptCategorySummary,
    summary="Rename one team-scoped prompt category.",
)
async def put_team_prompt_category(
    team_id: Annotated[TeamId, Path()],
    category_id: Annotated[str, Path(min_length=1)],
    body: UpdatePromptCategoryRequest,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PromptCategorySummary:
    """
    Rename one saved prompt category for the given team.

    Example:
    - `PUT /control-plane/v1/teams/bid-and-capture/prompt-categories/abc-123`
      `{ "name": "Relation client" }`
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        result = await update_prompt_category(team_id, category_id, body, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Category {category_id!r} not found for team {team_id!r}.",
        )
    return result


@router.delete(
    "/teams/{team_id}/prompt-categories/{category_id}",
    status_code=204,
    response_model=None,
    summary="Delete one team-scoped prompt category.",
)
async def delete_team_prompt_category(
    team_id: Annotated[TeamId, Path()],
    category_id: Annotated[str, Path(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """
    Delete one saved prompt category for the given team.

    Returns 409 when at least one prompt in the team still references this
    category — the caller must reassign or delete those prompts first.

    Example:
    - `DELETE /control-plane/v1/teams/bid-and-capture/prompt-categories/abc-123`
    """

    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_UPDATE_RESOURCES],
    )
    try:
        deleted = await delete_prompt_category(team_id, category_id, deps)
    except PromptRequestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Category {category_id!r} not found for team {team_id!r}.",
        )


@router.get(
    "/teams/{team_id}/agent-instances/{agent_instance_id}/runtime",
    response_model=ManagedAgentRuntimeBinding,
    response_model_exclude_none=True,
    summary="Resolve one managed agent instance into its runtime binding (team-scoped).",
)
async def get_team_agent_instance_runtime(
    team_id: Annotated[TeamId, Path()],
    agent_instance_id: Annotated[str, Path(min_length=1)],
    request: Request,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentRuntimeBinding:
    """
    Resolve one managed agent instance's runtime binding, scoped to one team.

    Why this endpoint exists (RUNTIME-07 rev. 2):
    - The runtime pod calls this at execution time to turn an `agent_instance_id`
      into its template + tuning. It is the team-scoped, ReBAC-gated replacement
      for the admin-only resolution path (finding F2): a plain team member with
      `CAN_READ` resolves their own team's instance, and resolution is restricted
      to the team via `store.get_for_team`, so no cross-tenant reach remains.
    - It returns config only (logical ids + tuning) — never a secret or a signed
      capability. End-user authorization is enforced independently at the pod
      (Keycloak JWT + OpenFGA); this endpoint adds team ReBAC as defense in depth.

    How to use it:
    - `GET /control-plane/v1/teams/{team_id}/agent-instances/{id}/runtime`

    TURN-01 correlation: the pod sends `X-Request-Id` on this call and times its
    own resolution as `runtime.stage_latency_ms{runtime_stage=runtime_binding}`
    with the same id as `trace.trace_id` — this handler mirrors that id on its
    own `runtime_binding_internal` stage so the two can be joined without
    relying on timestamp coincidence.
    """
    request_id = request.headers.get("X-Request-Id")
    async with runtime_stage_timer(
        deps.get_kpi_writer(), "runtime_binding_internal", trace_id=request_id
    ):
        team_id = await require_team_access(
            user,
            team_id,
            deps.team_dependencies,
            required_permissions=[TeamPermission.CAN_READ],
        )
        binding = await get_runtime_binding_for_team(agent_instance_id, team_id, deps)
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
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
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
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    return await list_sessions(team_id, user_id=user.uid, deps=deps)


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
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    item = await get_session(team_id=team_id, session_id=session_id, deps=deps)
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
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    updated = await update_session_activity(
        team_id=team_id,
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

    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    try:
        return await list_session_attachments(
            team_id=team_id,
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

    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    try:
        return await create_session_attachment(
            team_id=team_id,
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

    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    try:
        await delete_session_attachment(
            team_id=team_id,
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
    Delete one team-scoped conversation (CTRLP-12 A5).

    Hides the conversation immediately and erases it fully after the governed
    delete window (team `team_delete_grace`, personal platform
    `personal_delete_grace`); when no window is configured for the space the
    erase is immediate (back-compat). Runtime history is retained for the window.

    Returns 204 on success. Returns 404 when the session does not exist or is
    not owned by the caller (ownership is enforced up front, identical to the
    immediate-erase path).
    """
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    try:
        await delete_or_defer_session(
            team_id=team_id,
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
    team_id = await require_team_access(user, team_id, deps.team_dependencies)
    try:
        return await prepare_runtime_agent_execution(
            user=user,
            team_id=team_id,
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
    http_request: Request,
    user: KeycloakUser = Depends(get_current_user),
    session_id: str | None = None,
) -> ExecutionPreparation:
    """
    Prepare an execution context for one team-scoped managed agent instance.

    Does not proxy runtime SSE, expose cluster-internal hostnames, or execute the agent.

    Returns an ExecutionPreparation with ingress-relative URLs (and the resolved
    context prompt). RUNTIME-07 rev. 2: the control-plane issues NO signed grant —
    the pod authenticates the user (Keycloak JWT) and authorizes via OpenFGA.

    Pass ``session_id`` (query param) to include ``context_prompt_text`` in the response
    when the session has a context prompt configured. Library prompts are stored
    verbatim (language-agnostic).

    HITL resume needs no special preparation — the runtime derives the resume action
    from the request's ``resume_payload``.

    AUTHZ-05 post-implementation review finding: this used to fall back to the
    default ``CAN_READ`` (team_member or ``public``). Unlike the sibling
    ``get_team_agent_instance_runtime`` (deliberately kept on ``CAN_READ`` — it
    returns config only, never prompt content, real enforcement happens at the
    pod), this endpoint can return ``context_prompt_text`` — real prompt
    library content — directly from control-plane, before the pod is ever
    reached. Gated on ``CAN_USE_TEAM_AGENTS`` instead, the same team_member-only
    capability already required to list this team's agent instances in the
    first place (the natural next step in the same flow).
    """
    team_id = await require_team_access(
        user,
        team_id,
        deps.team_dependencies,
        required_permissions=[TeamPermission.CAN_USE_TEAM_AGENTS],
    )

    try:
        return await prepare_execution(
            user=user,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            session_id=session_id,
            deps=deps,
            # Forwarded to the pod's chat-controls evaluation so the pod-side
            # auth sees the acting user — same pattern as the validate-config
            # round-trip on enroll/update.
            authorization=http_request.headers.get("Authorization"),
        )
    except ExecutionPreparationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
