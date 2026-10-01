"""Verify historical folder owners and convert SQL ownership during maintenance.

Old knowledge-flow writers and authorization writers must be stopped. This is
one step of the coordinated corpus cutover, not a standalone rolling upgrade.
By default, only print the verified mapping. --apply commits all SQL changes in
one transaction, after every folder has passed verification. FGA is read-only.
"""

import argparse
import asyncio
import json

from fred_core import RebacDisabledResult, RebacReference, RelationType, Resource
from fred_core.common.team_id import personal_team_id
from fred_core.documents.tag_models import TagRow
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_core.sql.async_session import make_session_factory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def convert_owners(session: AsyncSession, rebac: RebacEngine, *, apply: bool = False) -> dict[str, str]:
    """Preflight the complete folder set before changing any owner in the session."""
    rows = list((await session.scalars(select(TagRow).order_by(TagRow.tag_id))).all())
    owners: dict[str, str] = {}
    errors: list[str] = []
    for row in rows:
        doc = row.doc or {}
        if row.type != "document" or not row.owner_id or any(doc.get(field) != getattr(row, field) for field in ("owner_id", "name", "path", "type")):
            errors.append(f"{row.tag_id}: missing SQL owner, SQL/JSON owner/path/type disagreement or non-document folder")
            continue
        resource = RebacReference(Resource.TAGS, row.tag_id)
        relations = await rebac.list_direct_relations(resource, consistency_token=RebacEngine.HIGHER_CONSISTENCY)
        if isinstance(relations, RebacDisabledResult):
            raise RuntimeError("Owner conversion requires an enabled ReBAC store; no ownership can be inferred.")
        explicit = [relation.subject for relation in relations if relation.resource == resource and relation.relation == RelationType.OWNER]
        if len(explicit) != 1 or explicit[0].type not in (Resource.USER, Resource.TEAM) or explicit[0].id != row.owner_id:
            errors.append(f"{row.tag_id}: missing, multiple or conflicting explicit ReBAC owner")
            continue
        owner = explicit[0]
        owners[row.tag_id] = personal_team_id(owner.id) if owner.type == Resource.USER else owner.id

    # User-owned and already personal-team-owned trees may converge onto the
    # same namespace. Reject collisions rather than merging existing folders.
    paths: dict[tuple[str, str], str] = {}
    for row in rows:
        if row.tag_id not in owners:
            continue
        full_path = f"{row.path}/{row.name}" if row.path else row.name
        if not full_path:
            errors.append(f"{row.tag_id}: missing folder name")
            continue
        key = (owners[row.tag_id], full_path)
        if key in paths:
            errors.append(f"{row.tag_id}, {paths[key]}: duplicate folder path after owner conversion")
        paths[key] = row.tag_id
    if errors:
        raise RuntimeError("Corpus owner conversion refused; no owners changed:\n" + "\n".join(errors))
    if apply:
        for row in rows:
            row.owner_id = owners[row.tag_id]
            row.doc = {**(row.doc or {}), "owner_id": row.owner_id}
        await session.flush()
    return owners


async def main(apply: bool) -> None:
    # Keep configuration/application startup out of the testable conversion.
    from fred_core import OpenFgaRebacConfig

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.common.config_loader import load_configuration

    configuration = load_configuration()
    if not isinstance(configuration.security.rebac, OpenFgaRebacConfig):
        raise RuntimeError("Owner conversion requires an enabled OpenFGA store.")
    configuration.security.rebac.create_store_if_needed = False
    configuration.security.rebac.sync_schema_on_init = False
    context = ApplicationContext(configuration)
    try:
        sessions = make_session_factory(context.get_async_sql_engine())
        async with sessions.begin() as session:
            mapping = await convert_owners(session, context.get_rebac_engine(), apply=apply)
        print(json.dumps({"applied": apply, "folder_team_owners": mapping}, indent=2))
    finally:
        await context.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit verified SQL owners; requires all corpus/authorization writers stopped.")
    asyncio.run(main(parser.parse_args().apply))
