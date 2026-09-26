"""Organization HTTP authorization and lifecycle against isolated SQLite stores."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from control_plane_backend.models.platform_prompt_models import PlatformPromptRow
from control_plane_backend.organizations import api
from control_plane_backend.organizations.store import OrganizationStore
from control_plane_backend.platform_prompt.store import PlatformPromptStore
from control_plane_backend.product.dependencies import get_product_service_dependencies
from fastapi import FastAPI, HTTPException
from fred_core import KeycloakUser, OrganizationPermission, get_current_user
from fred_core.sql import use_session
from fred_core.teams.organization_models import OrganizationRow
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy.ext.asyncio import create_async_engine


class ScopedPermissions:
    """Evaluate explicit grants and reject all other subject/permission/scope triples."""

    def __init__(self):
        self.grants = {
            ("platform", OrganizationPermission.CAN_MANAGE_ORGANIZATIONS, "fred"),
            ("admin-a", OrganizationPermission.CAN_LIST_ALL_TEAMS, "a"),
            ("admin-a", OrganizationPermission.CAN_ADMINISTER_ORGANIZATION, "a"),
            ("admin-a", OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT, "a"),
        }
        self.checked = []
        self.delete_all_relations_of_reference = AsyncMock()
        self.add_relation = AsyncMock()

    async def check_user_permission_or_raise(self, user, permission, resource_id):
        key = (user.uid, permission, resource_id)
        self.checked.append(key)
        if key not in self.grants:
            raise HTTPException(403, "Permission denied")


@pytest_asyncio.fixture
async def organization_api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in (
            OrganizationRow.metadata.tables["organizations"],
            TeamMetadataRow.metadata.tables["teammetadata"],
            PlatformPromptRow.metadata.tables["platform_prompt"],
        ):
            await connection.run_sync(table.create)
    store = OrganizationStore(engine)
    async with use_session(store.sessions) as session:
        session.add_all(
            [OrganizationRow(id=key, name=key) for key in ("fred", "a", "b")]
        )
    permissions = ScopedPermissions()
    prompt_store = PlatformPromptStore(engine)
    await prompt_store.set(organization_id="a", text="A only", updated_by="admin-a")
    await prompt_store.set(organization_id="b", text="B only", updated_by="admin-b")
    team_deps = SimpleNamespace(rebac=permissions)
    product_deps = SimpleNamespace(
        team_dependencies=team_deps, get_platform_prompt_store=lambda: prompt_store
    )
    container = SimpleNamespace(
        get_rebac_engine=lambda: permissions, get_pg_async_engine=lambda: engine
    )
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(api, "get_team_service_dependencies", lambda request: team_deps)
    app = FastAPI()
    app.include_router(api.router)
    identity = {"uid": "platform"}
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid=identity["uid"], username=identity["uid"], roles=[], email=None
    )
    app.dependency_overrides[get_product_service_dependencies] = lambda: product_deps
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            client=client, identity=identity, permissions=permissions, store=store
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_platform_creates_and_deletes_empty_organization(organization_api):
    ctx = organization_api
    created = await ctx.client.post("/organizations", json={"name": " Acme "})
    assert created.status_code == 201
    organization_id = created.json()["id"]
    assert created.json()["name"] == "Acme"
    assert (await ctx.store.get(organization_id)).name == "Acme"
    assert (
        await ctx.client.delete(f"/organizations/{organization_id}")
    ).status_code == 204
    assert await ctx.store.get(organization_id) is None
    assert (
        ctx.permissions.delete_all_relations_of_reference.await_args.args[0].id
        == organization_id
    )


@pytest.mark.asyncio
async def test_deletion_preserves_default_and_nonempty_organizations(organization_api):
    ctx = organization_api
    async with use_session(ctx.store.sessions) as session:
        session.add(OrganizationRow(id="with-team", name="With team"))
        await session.flush()
        session.add(
            TeamMetadataRow(id="team", name="Team", organization_id="with-team")
        )
    for organization_id in ("fred", "a", "with-team"):
        response = await ctx.client.delete(f"/organizations/{organization_id}")
        assert response.status_code == 409
        assert await ctx.store.get(organization_id) is not None
    ctx.permissions.delete_all_relations_of_reference.assert_not_awaited()


@pytest.mark.asyncio
async def test_scoped_admin_cannot_manage_platform_or_read_other_organization(
    organization_api,
):
    ctx = organization_api
    ctx.identity["uid"] = "admin-a"
    assert (await ctx.client.get("/organizations")).status_code == 403
    assert (
        await ctx.client.post("/organizations", json={"name": "Unauthorized"})
    ).status_code == 403
    assert (await ctx.client.delete("/organizations/b")).status_code == 403
    assert (await ctx.client.get("/organizations/b/teams")).status_code == 403
    assert (await ctx.client.get("/organizations/b/prompt")).status_code == 403
    assert (
        await ctx.client.put("/organizations/b/prompt", json={"text": "Wrong"})
    ).status_code == 403
    own_prompt = await ctx.client.get("/organizations/a/prompt")
    assert own_prompt.status_code == 200
    assert own_prompt.json()["text"] == "A only"
    assert (
        "admin-a",
        OrganizationPermission.CAN_LIST_ALL_TEAMS,
        "b",
    ) in ctx.permissions.checked
    assert (
        "admin-a",
        OrganizationPermission.CAN_EDIT_PLATFORM_PROMPT,
        "b",
    ) in ctx.permissions.checked


@pytest.mark.asyncio
async def test_organization_admin_assigns_member_only_in_own_organization(
    organization_api,
):
    ctx = organization_api
    ctx.identity["uid"] = "admin-a"
    assert (
        await ctx.client.put("/organizations/b/members/new-user")
    ).status_code == 403
    ctx.permissions.add_relation.assert_not_awaited()
    assert (
        await ctx.client.put("/organizations/a/members/new-user")
    ).status_code == 204
    relation = ctx.permissions.add_relation.await_args.args[0]
    assert relation.subject.id == "new-user"
    assert relation.resource.id == "a"
    assert relation.relation.value == "member"
