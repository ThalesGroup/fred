"""Default organization initialization; never grants access to future organizations."""

from fred_core import RebacEngine, RebacReference, Relation, RelationType, Resource
from fred_core.sql import use_session

from control_plane_backend.organizations.store import OrganizationStore


async def reconcile_default_organization(container) -> None:
    """Run before serving; retry SQL/FGA initialization under the existing DB lock."""
    store = OrganizationStore(container.get_pg_async_engine())
    rebac = container.get_rebac_engine()
    async with container.get_team_metadata_store().advisory_lock(
        "organization_bootstrap"
    ):
        async with use_session(store.sessions) as session:
            row = await store.ensure_default(
                container.configuration.platform.default_organization_name,
                session=session,
            )
            if not rebac.enabled or row.admin_migration_completed:
                return
            reference = RebacReference(Resource.ORGANIZATION, "fred")
            relations = await rebac.list_direct_relations(
                reference, consistency_token=RebacEngine.HIGHER_CONSISTENCY
            )
            grants = [
                Relation(
                    subject=relation.subject,
                    relation=RelationType.ORGANIZATION_ADMIN,
                    resource=reference,
                )
                for relation in relations
                if relation.relation == RelationType.PLATFORM_ADMIN
                and relation.subject.type == Resource.USER
            ]
            if grants:
                await rebac.add_relations(grants)
            row.admin_migration_completed = True


async def ensure_user_organizations(user, rebac) -> set[str]:
    """Keep explicit membership beyond team changes; welcome unassigned users to fred."""
    from fred_core import OrganizationPermission, is_service_agent

    if not rebac.enabled:
        return {"fred"}
    if is_service_agent(user):
        return set()
    subject = RebacReference(Resource.USER, user.uid)
    explicit = await rebac.list_relations(
        subject=subject,
        resource_type=Resource.ORGANIZATION,
        relation=RelationType.MEMBER,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
    direct_ids = {relation.resource.id for relation in explicit}
    organizations = await rebac.lookup_resources(
        subject,
        OrganizationPermission.MEMBER,
        Resource.ORGANIZATION,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
    organization_ids = {organization.id for organization in organizations} | direct_ids
    if not organization_ids:
        organization_ids = {"fred"}
    missing = organization_ids - direct_ids
    if missing:
        await rebac.add_relations(
            [
                Relation(
                    subject=subject,
                    relation=RelationType.MEMBER,
                    resource=RebacReference(Resource.ORGANIZATION, organization_id),
                )
                for organization_id in sorted(missing)
            ]
        )
    return organization_ids
