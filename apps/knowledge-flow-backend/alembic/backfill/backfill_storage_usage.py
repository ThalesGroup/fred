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

from fred_core.common.team_id import is_personal_team_id
from fred_core.documents.document_models import DocumentMetadataRow as MetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.filesystem.structures import FilesystemResourceInfo
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import load_configuration

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


async def calculate_ingested_documents_sizes(session: AsyncSession) -> tuple[dict[str, int], dict[str, int]]:
    """Compute corpus storage from canonical SQL folder owners; no ReBAC lookup."""
    user_doc_sizes: dict[str, int] = {}
    team_doc_sizes: dict[str, int] = {}
    rows = (await session.execute(select(MetadataRow))).scalars().all()
    tag_cache = {}
    for row in rows:
        if not row.folder_id:
            # Conversation attachments are outside corpus storage accounting.
            continue
        if row.folder_id not in tag_cache:
            tag_cache[row.folder_id] = await session.get(TagRow, row.folder_id)
        folder = tag_cache[row.folder_id]
        if not folder or not folder.owner_id or folder.owner_id in {"personal", "personal-"}:
            raise RuntimeError(f"Cannot write absolute storage counters: folder {row.folder_id} has no canonical team owner. Complete the ownership migration first.")
        size = ((row.doc or {}).get("file") or {}).get("file_size_bytes") or 0
        if is_personal_team_id(folder.owner_id):
            user_id = folder.owner_id.removeprefix("personal-")
            user_doc_sizes[user_id] = user_doc_sizes.get(user_id, 0) + size
        else:
            team_doc_sizes[folder.owner_id] = team_doc_sizes.get(folder.owner_id, 0) + size
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
            # AUTHZ-05 review item 9: `name` is now required. This script only
            # backfills storage totals, not team identity — fall back to the
            # id rather than pulling in a Keycloak lookup this script has no
            # wiring for.
            # #2433: `visibility` is deliberately NOT set here. This script
            # knows a team owns content, never what discoverability its admin
            # intended — so it takes the platform default (private) rather
            # than publishing a team on a guess. Consequence to know before
            # running it: a team that reaches this branch and was previously
            # marketplace-listed loses that listing on the next `GET /teams`
            # (`_list_teams` revokes the ReBAC `public` relation for any
            # private team). Re-publishing it is a team_admin action.
            team_row = TeamMetadataRow(id=team_id, name=team_id, current_resources_storage_size=total_size)
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

        # 1. Calculate S3 Workspace storage usage
        user_ws, team_ws = await calculate_workspace_sizes(fs)

        # 2. Calculate S3 Ingested Documents storage usage
        sessions = make_session_factory(db_engine)
        async with use_session(sessions) as session:
            user_docs, team_docs = await calculate_ingested_documents_sizes(session)

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
