import asyncio
import logging
import os
from collections.abc import Iterable

from fred_core import RebacReference, Relation, RelationType, Resource, split_realm_url
from keycloak import KeycloakAdmin

from app.application_context import ApplicationContext, get_configuration

logger = logging.getLogger(__name__)

_MEMBER_PAGE_SIZE = 200
_GROUP_PAGE_SIZE = 200


async def reconcile_keycloak_groups_with_rebac() -> None:
    """Synchronize Keycloak group memberships into the ReBAC engine."""
    admin = create_keycloak_admin()
    if not admin:
        logger.warning("Keycloak admin client could not be created; skipping reconciliation.")
        return

    groups = await _fetch_all_groups(admin)
    if not groups:
        logger.info("No Keycloak groups returned for reconciliation.")
        return

    rebac_engine = ApplicationContext.get_instance().get_rebac_engine()

    relation_semaphore = asyncio.Semaphore(8)  # To avoid spamming the rebac engine with concurrent writes
    for group in groups:
        await _sync_group_hierarchy(admin, rebac_engine, group, relation_semaphore=relation_semaphore)

    logger.info("Completed Keycloak group reconciliation (%d top-level groups).", len(groups))


def create_keycloak_admin() -> KeycloakAdmin | None:
    """Create a Keycloak admin client using the configured service account. Returns None if M2M security is not enabled."""
    config = get_configuration()
    m2m_security = config.security.m2m
    if not m2m_security or not m2m_security.enabled:
        return None

    client_secret = os.getenv("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET")
    if not client_secret:
        raise RuntimeError("KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET is not set; cannot reconcile groups.")

    try:
        server_url, realm = split_realm_url(str(m2m_security.realm_url))
    except ValueError as exc:
        raise RuntimeError("Invalid Keycloak realm URL configured; cannot reconcile groups.") from exc

    return KeycloakAdmin(
        server_url=_ensure_trailing_slash(server_url),
        realm_name=realm,
        client_id=m2m_security.client_id,
        client_secret_key=client_secret,
        user_realm_name=realm,
    )


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


async def _sync_group_hierarchy(
    admin: KeycloakAdmin,
    rebac_engine,
    group: dict,
    *,
    relation_semaphore: asyncio.Semaphore,
) -> None:
    group_id = group.get("id")
    if not group_id:
        logger.warning("Encountered Keycloak group without identifier: %s", group)
        return

    group_name = group.get("name", "<unnamed>")
    group_ref = RebacReference(Resource.GROUP, group_id)

    existing_user_ids = await _fetch_existing_membership_ids(rebac_engine, group_ref, Resource.USER)
    existing_group_ids = await _fetch_existing_membership_ids(rebac_engine, group_ref, Resource.GROUP)

    members = await _fetch_all_group_members(admin, group_id)
    await _reconcile_user_memberships(
        rebac_engine,
        group_ref,
        members,
        existing_user_ids,
        relation_semaphore,
        group_name=group_name,
    )

    detailed_group = await admin.a_get_group(group_id)
    subgroups = detailed_group.get("subGroups") or []
    subgroup_map = {sg["id"]: sg for sg in subgroups if sg.get("id")}
    await _reconcile_group_memberships(
        rebac_engine,
        group_ref,
        subgroup_map,
        existing_group_ids,
        relation_semaphore,
        group_name=group_name,
    )

    if subgroup_map:
        await asyncio.gather(
            *(
                _sync_group_hierarchy(
                    admin,
                    rebac_engine,
                    subgroup,
                    relation_semaphore=relation_semaphore,
                )
                for subgroup in subgroup_map.values()
            )
        )


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


async def _fetch_existing_membership_ids(rebac_engine, group_ref: RebacReference, subject_type: Resource) -> set[str]:
    subjects = await asyncio.to_thread(
        rebac_engine.lookup_subjects,
        group_ref,
        RelationType.MEMBER,
        subject_type,
    )
    return {subject.id for subject in subjects}


async def _reconcile_user_memberships(
    rebac_engine,
    group_ref: RebacReference,
    members: Iterable[dict],
    existing_user_ids: set[str],
    relation_semaphore: asyncio.Semaphore,
    *,
    group_name: str,
) -> None:
    desired_ids: set[str] = set()
    add_tasks = []

    for member in members:
        user_id = member.get("id")
        if not user_id:
            logger.debug("Skipping Keycloak member without identifier: %s", member)
            continue
        desired_ids.add(user_id)
        if user_id not in existing_user_ids:
            relation = Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.MEMBER,
                resource=group_ref,
            )
            add_tasks.append(_write_relation(rebac_engine, relation, relation_semaphore))

    remove_ids = existing_user_ids - desired_ids
    remove_tasks = [
        _delete_relation(
            rebac_engine,
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.MEMBER,
                resource=group_ref,
            ),
            relation_semaphore,
        )
        for user_id in remove_ids
    ]

    await asyncio.gather(*add_tasks, *remove_tasks) if (add_tasks or remove_tasks) else None

    logger.debug(
        "Group '%s': %d member adds, %d removals, %d total members.",
        group_name,
        len(add_tasks),
        len(remove_tasks),
        len(desired_ids),
    )


async def _reconcile_group_memberships(
    rebac_engine,
    group_ref: RebacReference,
    subgroup_map: dict[str, dict],
    existing_group_ids: set[str],
    relation_semaphore: asyncio.Semaphore,
    *,
    group_name: str,
) -> None:
    desired_ids = set(subgroup_map)
    add_ids = desired_ids - existing_group_ids
    remove_ids = existing_group_ids - desired_ids

    add_tasks = [
        _write_relation(
            rebac_engine,
            Relation(
                subject=RebacReference(Resource.GROUP, subgroup_id),
                relation=RelationType.MEMBER,
                resource=group_ref,
            ),
            relation_semaphore,
        )
        for subgroup_id in add_ids
    ]

    remove_tasks = [
        _delete_relation(
            rebac_engine,
            Relation(
                subject=RebacReference(Resource.GROUP, subgroup_id),
                relation=RelationType.MEMBER,
                resource=group_ref,
            ),
            relation_semaphore,
        )
        for subgroup_id in remove_ids
    ]

    if add_tasks or remove_tasks:
        await asyncio.gather(*add_tasks, *remove_tasks)

    if add_ids or remove_ids:
        logger.debug(
            "Group '%s': %d subgroup adds, %d removals, %d total subgroups.",
            group_name,
            len(add_ids),
            len(remove_ids),
            len(desired_ids),
        )


async def _write_relation(rebac_engine, relation: Relation, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        await asyncio.to_thread(rebac_engine.add_relation, relation)


async def _delete_relation(rebac_engine, relation: Relation, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        await asyncio.to_thread(rebac_engine.delete_relation, relation)


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"
