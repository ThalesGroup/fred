# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Knowledge Base publication: the one write a definition's own image performs.

Admin visibility and team enablement are NOT here. A published definition is
projected into the shared capability catalog as `kind="knowledge_base"` and
managed through the capability admin routes, exactly as an application is —
one surface, while the grant still lands on the `knowledge_base_definition`
ReBAC type. Publication is gated on the exact client bound to the definition,
never on a broad service role.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fred_core import (
    AssertedUser,
    KeycloakUser,
    PrincipalContext,
    TeamPermission,
    get_current_user,
    get_current_user_without_gcu,
    get_delegation_config,
    require_workload_caller,
)
from fred_core.common import TeamId
from fred_core.security.models import AuthorizationError
from fred_sdk.knowledge_base import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBaseDeclaration,
)
from fred_sdk.knowledge_base.models import KnowledgeBaseRunContext
from pydantic import ValidationError

from control_plane_backend.app.route_errors import map_error as _map_error
from control_plane_backend.knowledge_bases import service as knowledge_base_service
from control_plane_backend.knowledge_bases.instances import (
    KnowledgeBaseInstanceNotFound,
    KnowledgeBaseNotEnabled,
    UnknownDefinition,
)
from control_plane_backend.knowledge_bases.library import LibraryRequestFailed
from control_plane_backend.knowledge_bases.runs import (
    RunAccessDenied,
    RunNotFound,
    build_run_context,
)
from control_plane_backend.knowledge_bases.schemas import (
    KnowledgeBaseDefinitionChoice,
    KnowledgeBaseInstanceCreate,
    KnowledgeBaseInstanceFields,
    KnowledgeBaseInstanceSummary,
    KnowledgeBasePublicationRequest,
    KnowledgeBasePublicationResult,
)
from control_plane_backend.knowledge_bases.service import (
    KnowledgeBaseClientMismatch,
)
from control_plane_backend.knowledge_bases.store import KnowledgeBasePrefixConflict
from control_plane_backend.knowledge_bases.validation import (
    InstanceConfigurationInvalid,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.teams.service import require_team_access

router = APIRouter(tags=["Knowledge Bases"])

# Everything the instance surface raises, mapped to its own status by
# `route_errors.map_error` reading each exception's `http_status`.
_INSTANCE_ERRORS = (
    AuthorizationError,
    InstanceConfigurationInvalid,
    KnowledgeBaseInstanceNotFound,
    KnowledgeBaseNotEnabled,
    LibraryRequestFailed,
    UnknownDefinition,
)
ProductDependencies = Annotated[
    ProductServiceDependencies,
    Depends(get_product_service_dependencies),
]


@router.put(
    "/knowledge-bases/definitions/{name}",
    response_model=KnowledgeBasePublicationResult,
    summary="Publish a Knowledge Base declaration from its own image.",
    operation_id="publish_knowledge_base_definition",
)
async def put_knowledge_base_definition(
    name: Annotated[str, Path(min_length=1, pattern=KNOWLEDGE_BASE_ID_PATTERN)],
    body: KnowledgeBasePublicationRequest,
    deps: ProductDependencies,
    # Not `get_current_user`: that dependency enforces persisted GCU acceptance,
    # which is a human admission control. The publisher is a confidential client
    # with no user row and nobody to accept anything — it would always be 403.
    user: KeycloakUser = Depends(get_current_user_without_gcu),
) -> KnowledgeBasePublicationResult:
    """Idempotent upsert, so every deployment of the image replays it.

    The name addresses what is written, so it is the path. The prefix is in the
    body because it is a claim the image makes about itself — a name alone
    cannot say how much of it its contributor owns.
    """
    if get_delegation_config().enabled:
        require_workload_caller(user)
    try:
        declaration = KnowledgeBaseDeclaration(
            id=name,
            version=body.version,
            name=body.name,
            description=body.description,
            configuration_fields=body.configuration_fields,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return await knowledge_base_service.publish_definition(
            user=user, prefix=body.prefix, declaration=declaration, deps=deps
        )
    except (
        KnowledgeBaseClientMismatch,
        KnowledgeBasePrefixConflict,
        AuthorizationError,
    ) as exc:
        raise _map_error(exc) from exc


# ---------------------------------------------------------------------------
# Team instances: a folder that fills itself
# ---------------------------------------------------------------------------


@router.get(
    "/knowledge-bases/definitions",
    response_model=list[KnowledgeBaseDefinitionChoice],
    summary="Definitions this team may synchronize a folder from.",
)
async def list_knowledge_base_definitions(
    team_id: Annotated[str, Query(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[KnowledgeBaseDefinitionChoice]:
    """What a folder-creation form offers under "synchronized by".

    Distinct from the admin catalog on purpose: that one lists everything
    published, this one only what the caller's team was enabled for.
    """
    try:
        return await knowledge_base_service.definitions_a_team_may_use(
            user=user, team_id=team_id, deps=deps
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.get(
    "/knowledge-bases/definitions/{definition_id}/fields",
    response_model=KnowledgeBaseInstanceFields,
    summary="The two zones an instance form renders for one definition.",
)
async def get_definition_fields(
    definition_id: str,
    team_id: Annotated[str, Query(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> KnowledgeBaseInstanceFields:
    """Served from the stored declaration, so the form renders whether or not
    the definition's pod is running — and only to a member of a team it is
    enabled for, because a declaration names what a source expects."""
    try:
        return await knowledge_base_service.definition_fields(
            user=user, definition_id=definition_id, team_id=team_id, deps=deps
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.get(
    "/knowledge-bases/instances",
    response_model=list[KnowledgeBaseInstanceSummary],
    summary="Synchronized folders of one team.",
)
async def list_knowledge_base_instances(
    team_id: Annotated[str, Query(min_length=1)],
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> list[KnowledgeBaseInstanceSummary]:
    try:
        return await knowledge_base_service.list_instances_for_team(
            user=user, team_id=team_id, deps=deps
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.post(
    "/knowledge-bases/instances",
    response_model=KnowledgeBaseInstanceSummary,
    status_code=201,
    summary="Create a folder synchronized by a Knowledge Base.",
)
async def create_knowledge_base_instance(
    body: KnowledgeBaseInstanceCreate,
    request: Request,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> KnowledgeBaseInstanceSummary:
    """One gesture, four effects, or none.

    The caller's own token is forwarded to knowledge-flow, so the right to add
    a folder to this team is checked where it always is.
    """
    try:
        return await knowledge_base_service.create_instance_for_team(
            user=user,
            authorization=request.headers.get("Authorization", ""),
            body=body,
            deps=deps,
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.get(
    "/knowledge-bases/instances/{instance_id}",
    response_model=KnowledgeBaseInstanceSummary,
    summary="One synchronized folder.",
)
async def get_knowledge_base_instance(
    instance_id: str,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> KnowledgeBaseInstanceSummary:
    try:
        return await knowledge_base_service.read_instance_for_team(
            user=user, instance_id=instance_id, deps=deps
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.delete(
    "/knowledge-bases/instances/{instance_id}",
    status_code=204,
    summary="Delete a synchronized folder, its documents and its grant.",
)
async def delete_knowledge_base_instance(
    instance_id: str,
    request: Request,
    deps: ProductDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> None:
    """Stopping a synchronization while keeping what it brought is deliberately
    not offered: deleting the folder deletes its documents."""
    try:
        await knowledge_base_service.delete_instance_for_team(
            user=user,
            authorization=request.headers.get("Authorization", ""),
            instance_id=instance_id,
            deps=deps,
        )
    except _INSTANCE_ERRORS as exc:
        raise _map_error(exc) from exc


@router.get(
    "/knowledge-bases/definitions/{definition_id}/instances/{instance_id}"
    "/runs/{run_id}/context",
    response_model=KnowledgeBaseRunContext,
    operation_id="get_knowledge_base_run_context",
    summary="One run's configuration, for the pod serving it.",
)
async def get_knowledge_base_run_context(
    definition_id: str,
    instance_id: str,
    run_id: str,
    request: Request,
    deps: ProductDependencies,
    # Not `get_current_user`: the caller is a confidential client with no user
    # row, so persisted GCU acceptance would refuse it for ever.
    user: KeycloakUser | AssertedUser = Depends(get_current_user_without_gcu),
) -> KnowledgeBaseRunContext:
    """Authorized by the exact client this definition is bound to — never by a
    broad service role, since this is where a source's secrets are."""
    try:
        caller = user
        asserted: AssertedUser | None = None
        if get_delegation_config().enabled:
            context = getattr(request.state, "principal_context", None)
            if not isinstance(context, PrincipalContext) or not isinstance(
                context.subject, AssertedUser
            ):
                raise HTTPException(status_code=403, detail="delegated_grant_required")
            require_workload_caller(context.caller)
            if context.subject.run_id != run_id:
                raise HTTPException(status_code=403, detail="run_target_mismatch")
            caller = context.caller
            asserted = context.subject
        result = await build_run_context(
            user=cast(KeycloakUser, caller),
            definition_id=definition_id,
            instance_id=instance_id,
            run_id=run_id,
            deps=deps,
        )
        if get_delegation_config().enabled:
            await require_team_access(
                cast(KeycloakUser, asserted),
                TeamId(result.team_id),
                deps.team_dependencies,
                [TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES],
            )
        return result
    except (InstanceConfigurationInvalid, RunAccessDenied, RunNotFound) as exc:
        raise _map_error(exc) from exc
