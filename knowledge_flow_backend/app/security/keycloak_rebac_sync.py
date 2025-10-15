import asyncio
import logging
from typing import NamedTuple

from fred_core import RebacReference, Relation, RelationType, Resource
from keycloak import KeycloakAdmin

from app.application_context import ApplicationContext
from app.security.keycloack_admin_client import create_keycloak_admin

logger = logging.getLogger(__name__)

_MEMBER_PAGE_SIZE = 200
_GROUP_PAGE_SIZE = 200


# Represents a group membership, like a Relation, but in a hashable way (compatible with set operations)
class MembershipEdge(NamedTuple):
    subject_type: Resource
    subject_id: str
    group_id: str

    @classmethod
    def from_relation(cls, relation: Relation) -> "MembershipEdge":
        return cls(relation.subject.type, relation.subject.id, relation.resource.id)

    def to_relation(self) -> Relation:
        return Relation(
            subject=RebacReference(self.subject_type, self.subject_id),
            relation=RelationType.MEMBER,
            resource=RebacReference(Resource.GROUP, self.group_id),
        )


async def reconcile_keycloak_groups_with_rebac() -> None:
    """Synchronize Keycloak group memberships into the ReBAC engine."""
    # Create Keycloak and ReBAC clients
    admin = create_keycloak_admin()
    if not admin:
        logger.warning("Keycloak admin client could not be created; skipping reconciliation.")
        return
    rebac_engine = ApplicationContext.get_instance().get_rebac_engine()

    # Collect membership edges from both systems
    keycloak_edges = await _collect_keycloak_memberships(admin)
    spicedb_edges = await _collect_spicedb_memberships(rebac_engine)

    # Compute the diff
    edges_to_add = keycloak_edges - spicedb_edges
    edges_to_remove = spicedb_edges - keycloak_edges

    if not edges_to_add and not edges_to_remove:
        logger.info("Keycloak and SpiceDB membership graphs are already in sync.")
        return

    # Apply the diff with limited concurrency (to avoid overwhelming RebAC engine)
    relation_semaphore = asyncio.Semaphore(8)
    await _apply_membership_diff(rebac_engine, edges_to_add, edges_to_remove, relation_semaphore)

    logger.info("Completed Keycloak group reconciliation.")


async def _collect_spicedb_memberships(rebac_engine) -> set[MembershipEdge]:
    relations = await asyncio.to_thread(
        rebac_engine.list_relations,
        resource_type=Resource.GROUP,
        relation=RelationType.MEMBER,
    )
    return {MembershipEdge.from_relation(relation) for relation in relations}


async def _collect_keycloak_memberships(admin: KeycloakAdmin) -> set[MembershipEdge]:
    """Traverse Keycloak groups to collect all membership edges (user→group and group→group)."""

    groups = await _fetch_all_groups(admin)
    if not groups:
        logger.info("No Keycloak groups returned; membership set considered empty.")
        return set()

    edges: set[MembershipEdge] = set()
    stack = [group for group in groups if group.get("id")]
    seen_groups: set[str] = set()

    while stack:
        group = stack.pop()
        group_id = group.get("id")
        if not group_id or group_id in seen_groups:
            continue
        seen_groups.add(group_id)

        members = await _fetch_all_group_members(admin, group_id)
        for member in members:
            user_id = member.get("id")
            if not user_id:
                logger.debug("Skipping Keycloak member without identifier in group %s: %s", group_id, member)
                continue
            edges.add(MembershipEdge(Resource.USER, user_id, group_id))

        detailed_group = await admin.a_get_group(group_id)
        subgroups = detailed_group.get("subGroups") or []
        for subgroup in subgroups:
            subgroup_id = subgroup.get("id")
            if not subgroup_id:
                logger.debug("Skipping subgroup without identifier in group %s: %s", group_id, subgroup)
                continue
            edges.add(MembershipEdge(Resource.GROUP, subgroup_id, group_id))
            stack.append(subgroup)

    logger.info("Collected %d membership edges from Keycloak across %d groups.", len(edges), len(seen_groups))
    return edges


async def _fetch_all_groups(admin: KeycloakAdmin) -> list[dict]:
    groups: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _GROUP_PAGE_SIZE, "briefRepresentation": True})

        if not batch:
            break
        groups.extend(batch)
        if len(batch) < _GROUP_PAGE_SIZE:
            break
        offset += _GROUP_PAGE_SIZE

    return groups


async def _fetch_all_group_members(admin: KeycloakAdmin, group_id: str) -> list[dict]:
    members: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_group_members(group_id, {"first": offset, "max": _MEMBER_PAGE_SIZE})
        if not batch:
            break
        members.extend(batch)
        if len(batch) < _MEMBER_PAGE_SIZE:
            break
        offset += _MEMBER_PAGE_SIZE

    return members


async def _apply_membership_diff(
    rebac_engine,
    edges_to_add: set[MembershipEdge],
    edges_to_remove: set[MembershipEdge],
    semaphore: asyncio.Semaphore,
) -> None:
    tasks: list[asyncio.Task[None]] = []

    for edge in edges_to_add:
        tasks.append(asyncio.create_task(_write_relation(rebac_engine, edge.to_relation(), semaphore)))

    for edge in edges_to_remove:
        tasks.append(asyncio.create_task(_delete_relation(rebac_engine, edge.to_relation(), semaphore)))

    if tasks:
        await asyncio.gather(*tasks)

    logger.info(
        "Applied membership diff: %d additions, %d deletions.",
        len(edges_to_add),
        len(edges_to_remove),
    )


async def _write_relation(rebac_engine, relation: Relation, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        await asyncio.to_thread(rebac_engine.add_relation, relation)


async def _delete_relation(rebac_engine, relation: Relation, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        await asyncio.to_thread(rebac_engine.delete_relation, relation)
