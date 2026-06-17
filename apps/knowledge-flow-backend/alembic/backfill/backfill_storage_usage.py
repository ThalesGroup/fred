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
# See the License for the do governing permissions and
# limitations under the License.

"""
One-shot migration script to backfill team and user storage usage.

Computes the storage currently occupied by:
1. Workspace files stored in the S3 filesystem (users/* and teams/*).
2. Ingested documents stored in the S3 content store (resolved to user or team spaces).

And updates:
- 'current_resources_storage_size' in the 'users' table
- 'current_resources_storage_size' in the 'teammetadata' table
"""

import asyncio
import logging
import sys
import uuid as uuid_mod
from uuid import UUID

from fred_core import RebacDisabledResult, RebacReference, RelationType, Resource
from fred_core.documents.document_models import DocumentMetadataRow as MetadataRow
from fred_core.filesystem.structures import FilesystemResourceInfo
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import load_configuration
from knowledge_flow_backend.core.stores.tags.tag_models import TagRow

# Configure logging to output to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("backfill_storage_usage")


def parse_user_uuid(user_id_str: str) -> UUID:
    """Parse string user ID to UUID object with fallback DNS mapping for dev configurations."""
    try:
        return UUID(user_id_str)
    except ValueError:
        return uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, f"dev-user-{user_id_str}")


async def calculate_workspace_sizes(fs) -> tuple[dict[str, int], dict[str, int]]:
    """Scan S3 filesystem bucket recursively and return workspace file sizes for users and teams."""
    user_workspace_sizes = {}
    team_workspace_sizes = {}

    logger.info("Listing S3 workspace filesystem objects recursively...")
    try:
        # Lists all objects under empty prefix (entire bucket)
        results = await fs.list("")
        logger.info(f"Scan finished. Found {len(results)} filesystem entries.")

        for res in results:
            if res.type == FilesystemResourceInfo.FILE and res.size:
                parts = [p for p in res.path.split("/") if p]
                if len(parts) >= 2:
                    root_prefix = parts[0]
                    owner_id = parts[1]

                    if root_prefix == "users":
                        user_workspace_sizes[owner_id] = user_workspace_sizes.get(owner_id, 0) + res.size
                    elif root_prefix == "teams":
                        if owner_id.startswith("personal-"):
                            real_user_id = owner_id[9:]
                            user_workspace_sizes[real_user_id] = user_workspace_sizes.get(real_user_id, 0) + res.size
                        else:
                            team_workspace_sizes[owner_id] = team_workspace_sizes.get(owner_id, 0) + res.size

    except Exception as e:
        logger.error(f"Failed to scan workspace filesystem in S3: {e}")
        raise

    return user_workspace_sizes, team_workspace_sizes


async def calculate_ingested_documents_sizes(session: AsyncSession, rebac) -> tuple[dict[str, int], dict[str, int]]:
    """Query ingested documents, resolve their owners using tags & ReBAC, and return size aggregates."""
    user_doc_sizes = {}
    team_doc_sizes = {}

    # Get all metadata documents
    logger.info("Fetching ingested documents metadata from database...")
    result = await session.execute(select(MetadataRow))
    rows = result.scalars().all()
    logger.info(f"Loaded {len(rows)} documents metadata.")

    # Cache tags and team metadata existence to avoid duplicate queries
    tag_cache = {}
    team_existence_cache = {}

    for row in rows:
        doc = row.doc or {}
        file_meta = doc.get("file", {})
        doc_size = file_meta.get("file_size_bytes") or 0
        if doc_size <= 0:
            continue

        tag_ids = row.tag_ids or []
        if not tag_ids:
            # Document has no tags, fallback to author
            author = row.author or doc.get("identity", {}).get("author")
            if author:
                user_doc_sizes[author] = user_doc_sizes.get(author, 0) + doc_size
            continue

        # Each document can be tagged. We adjust storage for the tag owner.
        # If a document has multiple tags, its size is added to each owner.
        for tag_id in tag_ids:
            # 1. Get Tag
            if tag_id not in tag_cache:
                tag_row = await session.get(TagRow, tag_id)
                tag_cache[tag_id] = tag_row
            else:
                tag_row = tag_cache[tag_id]

            if not tag_row or not tag_row.owner_id:
                continue

            owner_id = tag_row.owner_id
            if owner_id == "personal":
                # Fallback to the author of the document
                author = row.author or doc.get("identity", {}).get("author")
                if author:
                    owner_id = author
                else:
                    continue

            # 2. Check ReBAC owner (teams)
            team_ids = []
            if rebac.enabled:
                try:
                    subjects = await rebac.lookup_subjects(RebacReference(type=Resource.TAGS, id=tag_id), RelationType.OWNER, Resource.TEAM)
                    if not isinstance(subjects, RebacDisabledResult) and subjects:
                        for sub in subjects:
                            if sub.id != "personal":
                                team_ids.append(sub.id)
                except Exception as exc:
                    logger.warning(f"ReBAC owner lookup failed for tag {tag_id}: {exc}")

            # 3. Fallback database lookup to confirm if owner_id is a team
            if not team_ids:
                if owner_id not in team_existence_cache:
                    team_meta_row = await session.get(TeamMetadataRow, owner_id)
                    team_existence_cache[owner_id] = team_meta_row is not None

                if team_existence_cache[owner_id]:
                    team_ids.append(owner_id)

            # 4. Attribute size
            if team_ids:
                for team_id in team_ids:
                    if team_id.startswith("personal-"):
                        real_user_id = team_id[9:]
                        user_doc_sizes[real_user_id] = user_doc_sizes.get(real_user_id, 0) + doc_size
                    else:
                        team_doc_sizes[team_id] = team_doc_sizes.get(team_id, 0) + doc_size
            else:
                if owner_id.startswith("personal-"):
                    real_user_id = owner_id[9:]
                    user_doc_sizes[real_user_id] = user_doc_sizes.get(real_user_id, 0) + doc_size
                else:
                    user_doc_sizes[owner_id] = user_doc_sizes.get(owner_id, 0) + doc_size

    return user_doc_sizes, team_doc_sizes


async def update_database(session: AsyncSession, user_totals: dict[str, int], team_totals: dict[str, int]) -> None:
    """Update current resources storage size for users and teams in the database."""
    logger.info("Updating database tables with computed storage usage...")

    # Update Users
    for user_id_str, total_size in user_totals.items():
        user_uuid = parse_user_uuid(user_id_str)
        user_row = await session.get(UserRow, user_uuid)

        action_msg = "updating" if user_row else "inserting new user row for"
        logger.info(f"[USER] User {user_id_str} (UUID: {user_uuid}): {action_msg} storage to {total_size} bytes")

        if user_row:
            user_row.current_resources_storage_size = total_size
        else:
            user_row = UserRow(id=user_uuid, gcuVersionAccepted=None, gcuAcceptedAt=None, current_resources_storage_size=total_size)
            session.add(user_row)

    # Update Teams
    for team_id, total_size in team_totals.items():
        team_row = await session.get(TeamMetadataRow, team_id)

        action_msg = "updating" if team_row else "inserting new team metadata for"
        logger.info(f"[TEAM] Team {team_id}: {action_msg} storage to {total_size} bytes")

        if team_row:
            team_row.current_resources_storage_size = total_size
        else:
            team_row = TeamMetadataRow(id=team_id, current_resources_storage_size=total_size)
            session.add(team_row)

    await session.commit()
    logger.info("Database changes committed successfully.")


async def main() -> None:
    logger.info("Starting storage backfill script...")

    try:
        config = load_configuration()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    try:
        ctx = ApplicationContext(config)
    except Exception as e:
        logger.error(f"Failed to initialize ApplicationContext: {e}")
        sys.exit(1)

    try:
        # Retrieve dependencies
        db_engine = ctx.get_async_sql_engine()
        fs = ctx.get_filesystem()
        rebac = ctx.get_rebac_engine()

        # 1. Calculate S3 Workspace storage usage
        user_ws, team_ws = await calculate_workspace_sizes(fs)

        # 2. Calculate S3 Ingested Documents storage usage
        sessions = make_session_factory(db_engine)
        async with use_session(sessions) as session:
            user_docs, team_docs = await calculate_ingested_documents_sizes(session, rebac)

            # 3. Aggregate results
            all_users = set(user_ws.keys()) | set(user_docs.keys())
            all_teams = set(team_ws.keys()) | set(team_docs.keys())

            user_totals = {}
            for uid in all_users:
                user_totals[uid] = user_ws.get(uid, 0) + user_docs.get(uid, 0)

            team_totals = {}
            for tid in all_teams:
                team_totals[tid] = team_ws.get(tid, 0) + team_docs.get(tid, 0)

            # Log calculation summary
            logger.info("--- CALCULATION SUMMARY ---")
            for uid in sorted(all_users):
                logger.info(f"User {uid}: Workspace={user_ws.get(uid, 0)} bytes | Documents={user_docs.get(uid, 0)} bytes | Total={user_totals[uid]} bytes")
            for tid in sorted(all_teams):
                logger.info(f"Team {tid}: Workspace={team_ws.get(tid, 0)} bytes | Documents={team_docs.get(tid, 0)} bytes | Total={team_totals[tid]} bytes")
            logger.info("---------------------------")

            # 4. Perform database updates
            await update_database(session, user_totals, team_totals)

        logger.info("Backfill process finished successfully.")

    except Exception as e:
        logger.exception(f"An error occurred during backfill: {e}")
        sys.exit(1)
    finally:
        logger.info("Shutting down ApplicationContext...")
        await ctx.shutdown()
        logger.info("Shutdown completed.")


if __name__ == "__main__":
    asyncio.run(main())
