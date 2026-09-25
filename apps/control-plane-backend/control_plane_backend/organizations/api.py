"""Backend organization registry; legacy APIs continue to target fred."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fred_core import (
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    get_current_user,
)
from fred_core.sql import use_session
from fred_core.teams.organization_models import OrganizationRow
from fred_core.teams.team_metatada_models import TeamMetadataRow
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.organizations.store import OrganizationStore
from control_plane_backend.platform_prompt.schemas import (
    PlatformPrompt,
    SetPlatformPromptRequest,
)
from control_plane_backend.platform_prompt.service import (
    get_platform_prompt,
    set_platform_prompt,
)
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)
from control_plane_backend.teams.dependencies import get_team_service_dependencies
from control_plane_backend.teams.schemas import (
    CreateTeamRequest,
    Team,
    TeamWithPermissions,
)
from control_plane_backend.teams.service import create_team, list_all_teams_for_registry
from control_plane_backend.users.schemas import UserSummary

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationInput(BaseModel):
    """Organization label; identity is generated once and never renamed."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=180)


class OrganizationView(OrganizationInput):
    """Organization registry entry, containing no team content."""

    model_config = ConfigDict(from_attributes=True)
    id: str


async def _platform(request: Request, user: KeycloakUser) -> OrganizationStore:
    """Authorize organization lifecycle without granting organization content access."""
    container = get_application_container(request)
    await container.get_rebac_engine().check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_ORGANIZATIONS, "fred"
    )
    return OrganizationStore(container.get_pg_async_engine())


@router.get("", response_model=list[OrganizationView])
async def list_organizations(
    request: Request, user: KeycloakUser = Depends(get_current_user)
):
    """List the organization registry for a platform administrator."""
    return await (await _platform(request, user)).list()


@router.post("", response_model=OrganizationView, status_code=201)
async def create_organization(
    body: OrganizationInput,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Create an empty organization without giving its creator content permissions."""
    store = await _platform(request, user)
    async with use_session(store.sessions) as session:
        row = OrganizationRow(
            id=uuid4().hex, name=body.name, admin_migration_completed=True
        )
        session.add(row)
        await session.flush()
        return OrganizationView.model_validate(row)


@router.patch("/{organization_id}", response_model=OrganizationView)
async def rename_organization(
    organization_id: str,
    body: OrganizationInput,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Rename an organization without changing its identity or authorizations."""
    store = await _platform(request, user)
    async with use_session(store.sessions) as session:
        row = await session.get(OrganizationRow, organization_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, "Organization not found")
        row.name = body.name
        return OrganizationView.model_validate(row)


@router.delete("/{organization_id}", status_code=204)
async def delete_organization(
    organization_id: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Delete an empty non-default organization, refusing implicit cascading erasure."""
    store = await _platform(request, user)
    if organization_id == "fred":
        raise HTTPException(409, "The default organization cannot be deleted")
    from control_plane_backend.models.platform_prompt_models import PlatformPromptRow

    async with use_session(store.sessions) as session:
        row = await session.get(OrganizationRow, organization_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, "Organization not found")
        team = await session.scalar(
            select(TeamMetadataRow.id)
            .where(TeamMetadataRow.organization_id == organization_id)
            .limit(1)
        )
        prompt = await session.get(PlatformPromptRow, organization_id)
        if team is not None or prompt is not None:
            raise HTTPException(409, "Organization is not empty")
        await (
            get_application_container(request)
            .get_rebac_engine()
            .delete_all_relations_of_reference(
                RebacReference(Resource.ORGANIZATION, organization_id)
            )
        )
        await session.delete(row)
    return Response(status_code=204)


@router.put("/{organization_id}/administrators/{user_id}", status_code=204)
async def grant_admin(
    organization_id: str,
    user_id: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Grant an explicit organization role, independent of platform privileges."""
    store = await _platform(request, user)
    async with use_session(store.sessions) as session:
        if (
            await session.get(OrganizationRow, organization_id, with_for_update=True)
            is None
        ):
            raise HTTPException(404, "Organization not found")
        await (
            get_application_container(request)
            .get_rebac_engine()
            .add_relation(
                Relation(
                    subject=RebacReference(Resource.USER, user_id),
                    relation=RelationType.ORGANIZATION_ADMIN,
                    resource=RebacReference(Resource.ORGANIZATION, organization_id),
                ),
                actor_uid=user.uid,
            )
        )
    return Response(status_code=204)


@router.delete("/{organization_id}/administrators/{user_id}", status_code=204)
async def revoke_admin(
    organization_id: str,
    user_id: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Revoke an explicit role; startup must not restore it after completed migration."""
    store = await _platform(request, user)
    async with use_session(store.sessions) as session:
        if (
            await session.get(OrganizationRow, organization_id, with_for_update=True)
            is None
        ):
            raise HTTPException(404, "Organization not found")
        await (
            get_application_container(request)
            .get_rebac_engine()
            .delete_relation(
                Relation(
                    subject=RebacReference(Resource.USER, user_id),
                    relation=RelationType.ORGANIZATION_ADMIN,
                    resource=RebacReference(Resource.ORGANIZATION, organization_id),
                )
            )
        )
    return Response(status_code=204)


@router.get("/{organization_id}/teams", response_model=list[Team])
async def organization_teams(
    organization_id: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """List only this organization's team registry."""
    return await list_all_teams_for_registry(
        user, get_team_service_dependencies(request), organization_id=organization_id
    )


@router.post(
    "/{organization_id}/teams", response_model=TeamWithPermissions, status_code=201
)
async def create_organization_team(
    organization_id: str,
    body: CreateTeamRequest,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Create a team in an explicit organization with existing team-role semantics."""
    return await create_team(
        user,
        body,
        get_team_service_dependencies(request),
        organization_id=organization_id,
    )


@router.get("/{organization_id}/prompt", response_model=PlatformPrompt)
async def read_prompt(
    organization_id: str,
    deps: Annotated[
        ProductServiceDependencies, Depends(get_product_service_dependencies)
    ],
    user: KeycloakUser = Depends(get_current_user),
):
    """Read the prompt administered by this organization."""
    return await get_platform_prompt(
        user=user, deps=deps, organization_id=organization_id
    )


@router.put("/{organization_id}/prompt", response_model=PlatformPrompt)
async def write_prompt(
    organization_id: str,
    body: SetPlatformPromptRequest,
    deps: Annotated[
        ProductServiceDependencies, Depends(get_product_service_dependencies)
    ],
    user: KeycloakUser = Depends(get_current_user),
):
    """Set the organization prompt without changing global model configuration."""
    return await set_platform_prompt(
        user=user, text=body.text, deps=deps, organization_id=organization_id
    )


@router.get(
    "/{organization_id}/candidate-team-admins", response_model=list[UserSummary]
)
async def candidate_admins(
    organization_id: str,
    query: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Reuse bounded candidate lookup for scoped team creation."""
    from control_plane_backend.teams.service import search_candidate_team_admins

    return await search_candidate_team_admins(
        user,
        query,
        get_team_service_dependencies(request),
        organization_id=organization_id,
    )


@router.put("/{organization_id}/members/{user_id}", status_code=204)
async def grant_member(
    organization_id: str,
    user_id: str,
    request: Request,
    user: KeycloakUser = Depends(get_current_user),
):
    """Assign organization membership independently of team membership."""
    container = get_application_container(request)
    rebac = container.get_rebac_engine()
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_ADMINISTER_ORGANIZATION, organization_id
    )
    store = OrganizationStore(container.get_pg_async_engine())
    async with use_session(store.sessions) as session:
        if (
            await session.get(OrganizationRow, organization_id, with_for_update=True)
            is None
        ):
            raise HTTPException(404, "Organization not found")
        await rebac.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.MEMBER,
                resource=RebacReference(Resource.ORGANIZATION, organization_id),
            ),
            actor_uid=user.uid,
        )
    return Response(status_code=204)
