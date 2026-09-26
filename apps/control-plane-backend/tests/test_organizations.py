"""Upgrade compatibility and organization prompt isolation using real offline stores."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
from control_plane_backend.models.platform_prompt_models import PlatformPromptRow
from control_plane_backend.organizations.service import reconcile_default_organization
from control_plane_backend.organizations.store import OrganizationStore
from control_plane_backend.platform_prompt.service import resolve_platform_prompt_text
from control_plane_backend.platform_prompt.store import PlatformPromptStore
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.common import TeamId
from fred_core.sql import use_session
from fred_core.teams.metadata_store import TeamMetadataStore
from fred_core.teams.organization_models import OrganizationRow
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def engine():
    """Use isolated tables, never a developer's configured database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            OrganizationRow.metadata.tables["organizations"],
            TeamMetadataRow.metadata.tables["teammetadata"],
            PlatformPromptRow.metadata.tables["platform_prompt"],
        ):
            await connection.run_sync(table.create)
    yield engine
    await engine.dispose()


class Grants:
    """Model durable grants independently of SQL rollback for migration failure tests."""

    enabled = True

    def __init__(self):
        self.relations = [
            Relation(
                subject=RebacReference(Resource.USER, "existing-admin"),
                relation=RelationType.PLATFORM_ADMIN,
                resource=RebacReference(Resource.ORGANIZATION, "fred"),
            )
        ]
        self.fail_after_write = False

    async def list_direct_relations(self, reference, **kwargs):
        return list(self.relations)

    async def add_relations(self, relations):
        for relation in relations:
            if relation not in self.relations:
                self.relations.append(relation)
        if self.fail_after_write:
            self.fail_after_write = False
            raise RuntimeError("Interrupted after FGA write")


@asynccontextmanager
async def lock(_key):
    """Single-process SQLite test substitute; production uses a Postgres lock."""
    yield


def container(engine, grants, name="Acme"):
    """Wire actual persistence and controllable external grants into startup."""
    return SimpleNamespace(
        get_pg_async_engine=lambda: engine,
        get_rebac_engine=lambda: grants,
        get_team_metadata_store=lambda: SimpleNamespace(advisory_lock=lock),
        configuration=SimpleNamespace(
            platform=SimpleNamespace(default_organization_name=name)
        ),
    )


@pytest.mark.asyncio
async def test_upgrade_retries_then_preserves_role_revocation(engine):
    """An interrupted dual-store migration retries without permanent role inheritance."""
    grants = Grants()
    grants.fail_after_write = True
    with pytest.raises(RuntimeError, match="Interrupted"):
        await reconcile_default_organization(container(engine, grants))
    await reconcile_default_organization(container(engine, grants))
    organization = await OrganizationStore(engine).get("fred")
    assert organization is not None
    assert organization.name == "Acme"
    assert organization.admin_migration_completed
    assert {r.relation for r in grants.relations} == {
        RelationType.PLATFORM_ADMIN,
        RelationType.ORGANIZATION_ADMIN,
    }
    grants.relations = [
        r for r in grants.relations if r.relation != RelationType.ORGANIZATION_ADMIN
    ]
    await reconcile_default_organization(container(engine, grants, "Renamed"))
    assert len(grants.relations) == 1
    renamed = await OrganizationStore(engine).get("fred")
    assert renamed is not None
    assert renamed.name == "Renamed"


@pytest.mark.asyncio
async def test_runtime_selects_team_prompt_and_never_leaks_default(engine):
    """Explicit empty and absent non-default prompts must suppress legacy fallback."""
    store = OrganizationStore(engine)
    async with use_session(store.sessions) as session:
        session.add_all(
            [
                OrganizationRow(id="fred", name="Fred"),
                OrganizationRow(id="other", name="Other"),
            ]
        )
    teams = TeamMetadataStore(engine)
    await teams.create(TeamId("a"), "A")
    await teams.create(TeamId("b"), "B", organization_id="other")
    prompts = PlatformPromptStore(engine)
    await prompts.set(text="Original production text", updated_by="existing-admin")
    deps = cast(
        ProductServiceDependencies,
        SimpleNamespace(
            get_team_metadata_store=lambda: teams,
            get_platform_prompt_store=lambda: prompts,
        ),
    )
    assert await resolve_platform_prompt_text(deps, "a") == "Original production text"
    assert await resolve_platform_prompt_text(deps, "b") == ""
    await prompts.set(
        text="Other instructions", updated_by="other-admin", organization_id="other"
    )
    assert await resolve_platform_prompt_text(deps, "b") == "Other instructions"
    await prompts.set(text="", updated_by="existing-admin")
    assert await resolve_platform_prompt_text(deps, "a") == ""
    with pytest.raises(ValueError, match="unknown team"):
        await resolve_platform_prompt_text(deps, "missing")


@pytest.mark.asyncio
async def test_no_dependent_rows_for_missing_organization(engine):
    """Creation cannot bypass the organization registry using an arbitrary ID."""
    with pytest.raises(ValueError, match="Organization does not exist"):
        await TeamMetadataStore(engine).create(
            TeamId("a"), "A", organization_id="missing"
        )
    with pytest.raises(ValueError, match="Organization does not exist"):
        await PlatformPromptStore(engine).set(
            text="x", updated_by="u", organization_id="missing"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial,derived", [(set(), set()), ({"other"}, set()), (set(), {"other"})]
)
async def test_user_membership_is_explicit_without_teams_and_retryable(
    initial, derived
):
    """New users enter fred; preassigned users never acquire another organization."""
    from control_plane_backend.organizations.service import ensure_user_organizations
    from fred_core import KeycloakUser

    class Memberships:
        enabled = True

        def __init__(self):
            self.direct = set(initial)
            self.writes = 0
            self.derived = set(derived)

        async def list_relations(self, *, subject, **kwargs):
            return [
                Relation(
                    subject=subject,
                    relation=RelationType.MEMBER,
                    resource=RebacReference(Resource.ORGANIZATION, org),
                )
                for org in self.direct
            ]

        async def lookup_resources(self, *args, **kwargs):
            return [
                RebacReference(Resource.ORGANIZATION, org)
                for org in self.direct | self.derived
            ]

        async def add_relations(self, relations):
            self.writes += 1
            self.direct.update(r.resource.id for r in relations)

    rebac = Memberships()
    user = KeycloakUser(uid="new-user", username="new-user", roles=[])
    expected = initial or derived or {"fred"}
    assert await ensure_user_organizations(user, rebac) == expected
    rebac.derived.clear()  # Leaving the last team must not remove organization membership.
    assert await ensure_user_organizations(user, rebac) == expected
    assert rebac.direct == expected
    assert rebac.writes == (0 if initial else 1)
