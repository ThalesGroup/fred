"""
backfill_agent_kf_vector_search_tags.py

ONE-TIME BACKFILL — companion to Alembic migration
  5978e4ad3e1b_backfill_agent_kf_vector_search_mcp_params

Run this ONCE per cluster after deploying that migration.
It replaces the empty document_library_tags_ids (set by the migration)
with the actual list of tag IDs the agent can read, resolved via ReBAC.

This script is NOT intended to be maintained long-term.
Once all clusters have been updated it can be deleted.

Prerequisites:
  Both agentic-backend and knowledge-flow-backend installed in the same
  Python environment (they share the same PostgreSQL database).

Usage:
  CONFIG_FILE=<path> python backfill_agent_kf_vector_search_tags.py [options]

Options:
  --dry-run          Print proposed changes; do not write anything.
  --agent-id <id>    Process only this agent (useful for debugging).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from copy import deepcopy

from fred_core import (
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    RelationType,
    Resource,
    TagPermission,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.common.structures import Agent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

KF_MCP_TEXT_SERVER_ID = "mcp-knowledge-flow-mcp-text"


# ---------------------------------------------------------------------------
# Tag resolution via ReBAC
# ---------------------------------------------------------------------------


async def _get_all_tag_ids(pg_async_engine: AsyncEngine) -> list[str]:
    """Fallback used when ReBAC is disabled: return all tag IDs from the tag table."""

    async with AsyncSession(pg_async_engine) as session:
        rows = (await session.execute(text("SELECT tag_id FROM tag"))).fetchall()
    return [r[0] for r in rows]


async def _resolve_tag_ids(
    rebac: RebacEngine, agent: Agent, pg_async_engine: AsyncEngine
) -> list[str]:
    """
    Resolve the tag IDs the agent should have access to via OWNER, EDITOR, or VIEWER relations.

    For team agents: all tags the team owns, edits, or views.
    For personal agents: all tags the owner user owns, edits, or views.
    Falls back to all tags when ReBAC is disabled; returns [] for orphaned personal agents.
    """
    team_id = agent.team_id

    if team_id:
        subject_ref = RebacReference(type=Resource.TEAM, id=team_id)
    else:
        owner_refs = await rebac.lookup_subjects(
            resource=RebacReference(type=Resource.AGENT, id=agent.id),
            relation=RelationType.OWNER,
            subject_type=Resource.USER,
        )
        if isinstance(owner_refs, RebacDisabledResult):
            logger.info(
                "[BACKFILL] ReBAC disabled for agent %s — using all tags", agent.id
            )
            return await _get_all_tag_ids(pg_async_engine)
        if not owner_refs:
            logger.warning(
                "[BACKFILL] Agent %s has no owner in ReBAC — using []", agent.id
            )
            return []
        subject_ref = RebacReference(type=Resource.USER, id=owner_refs[0].id)

    owned, edited, viewed = await asyncio.gather(
        rebac.lookup_resources(subject_ref, TagPermission.OWNER, Resource.TAGS),
        rebac.lookup_resources(subject_ref, TagPermission.EDITOR, Resource.TAGS),
        rebac.lookup_resources(subject_ref, TagPermission.VIEWER, Resource.TAGS),
    )

    if (
        isinstance(owned, RebacDisabledResult)
        or isinstance(edited, RebacDisabledResult)
        or isinstance(viewed, RebacDisabledResult)
    ):
        logger.info("[BACKFILL] ReBAC disabled for agent %s — using all tags", agent.id)
        return await _get_all_tag_ids(pg_async_engine)

    return list({ref.id for refs in (owned, edited, viewed) for ref in refs})


# ---------------------------------------------------------------------------
# Backfill logic
# ---------------------------------------------------------------------------


def _needs_backfill(agent) -> bool:
    """True if the agent has an mcp-knowledge-flow-mcp-text entry with empty tag IDs."""
    tuning = agent.tuning
    if tuning is None:
        return False
    for srv in tuning.mcp_servers or []:
        if srv.id != KF_MCP_TEXT_SERVER_ID:
            continue
        if srv.params is None:
            return True
        tag_ids = getattr(srv.params, "document_library_tags_ids", None)
        if tag_ids is not None and len(tag_ids) == 0:
            return True
    return False


def _current_tag_ids(agent) -> list[str] | None:
    """Return the current document_library_tags_ids for the KF MCP server, or None if unset."""
    for srv in agent.tuning.mcp_servers or []:
        if srv.id == KF_MCP_TEXT_SERVER_ID and srv.params is not None:
            return getattr(srv.params, "document_library_tags_ids", None)
    return None


def _apply_tag_ids(agent, tag_ids: list[str]):
    """Return a copy of the agent with document_library_tags_ids set on matching servers."""
    updated = deepcopy(agent)
    for srv in updated.tuning.mcp_servers or []:
        if srv.id != KF_MCP_TEXT_SERVER_ID:
            continue
        if srv.params is None:
            continue
        srv.params.document_library_tags_ids = list(tag_ids)
    return updated


async def run_backfill(*, dry_run: bool, agent_id_filter: str | None) -> None:
    from agentic_backend.application_context import (
        ApplicationContext,
        get_agent_store,
        get_pg_async_engine,
        get_rebac_engine,
    )
    from agentic_backend.common.config_loader import load_configuration
    from agentic_backend.core.agents.agent_spec import AgentTuning

    cfg = load_configuration()
    context = ApplicationContext(cfg)
    rebac = get_rebac_engine()
    agent_store = get_agent_store()
    pg_engine = get_pg_async_engine()

    agents = await agent_store.load_all()

    if agent_id_filter:
        agents = [a for a in agents if a.id == agent_id_filter]
        if not agents:
            logger.error("[BACKFILL] No agent found with id=%s", agent_id_filter)
            sys.exit(1)

    backfill_count = 0
    skip_count = 0
    error_count = 0

    for agent in agents:
        if not _needs_backfill(agent):
            skip_count += 1
            continue

        try:
            tag_ids = await _resolve_tag_ids(rebac, agent, pg_engine)
        except Exception:
            logger.exception(
                "[BACKFILL] Failed to resolve tags for agent %s — skipping", agent.id
            )
            error_count += 1
            continue

        current_tag_ids = _current_tag_ids(agent)
        if current_tag_ids is not None and set(current_tag_ids) == set(tag_ids):
            logger.info(
                "[BACKFILL] Agent %s (%s): already has %d tag ID(s), skipping",
                agent.id,
                agent.name,
                len(tag_ids),
            )
            skip_count += 1
            continue

        logger.info(
            "[BACKFILL] Agent %s (%s): will set %d tag ID(s)%s",
            agent.id,
            agent.name,
            len(tag_ids),
            " [DRY-RUN]" if dry_run else "",
        )

        if not dry_run:
            updated_agent = _apply_tag_ids(agent, tag_ids)
            tuning: AgentTuning = updated_agent.tuning  # type: ignore[assignment]
            await agent_store.save(updated_agent, tuning)

        backfill_count += 1

    logger.info(
        "[BACKFILL] Done. Updated: %d  |  Skipped (no change needed): %d  |  Errors: %d%s",
        backfill_count,
        skip_count,
        error_count,
        " [DRY-RUN — no writes performed]" if dry_run else "",
    )

    await context.shutdown()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time backfill: populate document_library_tags_ids on agents "
            "that use mcp-knowledge-flow-mcp-text."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed changes without writing.",
    )
    parser.add_argument(
        "--agent-id",
        metavar="ID",
        default=None,
        help="Process only this agent ID (for debugging).",
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(dry_run=args.dry_run, agent_id_filter=args.agent_id))


if __name__ == "__main__":
    main()
