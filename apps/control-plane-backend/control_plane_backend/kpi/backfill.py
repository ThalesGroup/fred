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
# See the License for the specific language governing permissions and
# limitations under the License.

"""Operator command completing past KPI events, never run at startup: reindex
turns so newly mapped fields become searchable, and attribute past human API
requests to a team (day-level approximation, UTC days). Both steps are idempotent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterator

from fred_core import (
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    RelationType,
    Resource,
)
from fred_core.common.team_id import is_personal_team_id
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.session_metadata_models import SessionMetadataRow

logger = logging.getLogger(__name__)

TURN_METRIC = "agent.turn_completed"
API_METRIC = "api.request_latency_ms"
_PAGE_SIZE = 1000

# Only sets an absent team; the day key is the UTC date of the event.
TEAM_SCRIPT = (
    "if (ctx._source.dims == null) { ctx._source.dims = [:]; } "
    "if (ctx._source.dims.team_id == null) { "
    "String d = ctx._source['@timestamp'].toString().substring(0, 10); "
    "def t = params.days.get(d); "
    "if (t == null) { t = params.fallback; } "
    "if (t != null) { ctx._source.dims.team_id = t; } else { ctx.op = 'noop'; } "
    "} else { ctx.op = 'noop'; }"
)


@dataclass
class UserSessions:
    """Non-personal session counts of one user, per UTC day and overall."""

    per_day: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    overall: Counter[str] = field(default_factory=Counter)


def _best_team(counts: Counter[str], candidates: set[str] | None = None) -> str | None:
    """Most sessions wins; ties and zero counts go to the smallest team id."""
    pool = candidates if candidates is not None else set(counts)
    return min(pool, key=lambda team: (-counts.get(team, 0), team), default=None)


def day_to_team(sessions: UserSessions) -> dict[str, str]:
    return {
        day: team
        for day, counts in sessions.per_day.items()
        if (team := _best_team(counts)) is not None
    }


def fallback_team(sessions: UserSessions, member_teams: set[str]) -> str | None:
    teams = {t for t in member_teams if not is_personal_team_id(t)}
    if len(teams) <= 1:
        return next(iter(teams), None)
    return _best_team(sessions.overall, teams)


async def load_user_sessions(
    engine: AsyncEngine, since: datetime | None
) -> dict[str, UserSessions]:
    """One streamed pass over `session_metadata`, soft-deleted rows included."""
    stmt = select(
        SessionMetadataRow.user_id,
        SessionMetadataRow.team_id,
        SessionMetadataRow.created_at,
        SessionMetadataRow.updated_at,
    ).where(
        SessionMetadataRow.user_id.is_not(None),
        SessionMetadataRow.team_id.not_like("personal-%"),
    )
    if since is not None:
        stmt = stmt.where(SessionMetadataRow.updated_at >= since)
    result: dict[str, UserSessions] = defaultdict(UserSessions)
    async with engine.connect() as conn:
        rows = await conn.stream(stmt)
        async for user_id, team_id, created_at, updated_at in rows:
            if user_id is None:  # excluded by the query; narrows the type
                continue
            entry = result[user_id]
            entry.overall[team_id] += 1
            for day in {_utc_day(created_at), _utc_day(updated_at)}:
                entry.per_day[day][team_id] += 1
    return result


def _utc_day(value: datetime) -> str:
    # SQLite returns naive datetimes that are already UTC.
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.date().isoformat()


async def member_teams(rebac: RebacEngine, user_id: str) -> set[str]:
    refs = await rebac.lookup_resources(
        RebacReference(Resource.USER, user_id),
        RelationType.TEAM_MEMBER,
        Resource.TEAM,
    )
    if isinstance(refs, RebacDisabledResult):
        return set()
    return {ref.id for ref in refs}


def _since_filter(since: datetime | None) -> list[dict[str, Any]]:
    return [{"range": {"@timestamp": {"gte": since.isoformat()}}}] if since else []


def _missing_team_query(
    since: datetime | None, user_id: str | None = None
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [
        {"term": {"metric.name": API_METRIC}},
        {"term": {"dims.actor_type": "human"}},
        *_since_filter(since),
    ]
    if user_id is not None:
        filters.append({"term": {"dims.user_id": user_id}})
    return {
        "bool": {
            "filter": filters,
            "must_not": [{"exists": {"field": "dims.team_id"}}],
        }
    }


def users_missing_team(
    store: OpenSearchKPIStore, since: datetime | None
) -> Iterator[tuple[str, int]]:
    """Yield `(user_id, event_count)` for users with unattributed API events."""
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE_SIZE,
            "sources": [{"user": {"terms": {"field": "dims.user_id"}}}],
        }
        if after:
            composite["after"] = after
        body = {
            "size": 0,
            "query": _missing_team_query(since),
            "aggs": {"users": {"composite": composite}},
        }
        agg = store.client.search(index=store.index, body=body)["aggregations"]["users"]
        for bucket in agg["buckets"]:
            yield bucket["key"]["user"], int(bucket["doc_count"])
        after = agg.get("after_key")
        if not after or len(agg["buckets"]) < _PAGE_SIZE:
            return


def run_update_by_query(
    store: OpenSearchKPIStore, body: dict[str, Any], poll_seconds: float
) -> int:
    """Start an async `update_by_query` task and wait for its `updated` count."""
    started = store.client.update_by_query(
        index=store.index,
        body=body,
        params={
            "conflicts": "proceed",
            "slices": "auto",
            "wait_for_completion": "false",
        },
    )
    task_id = started["task"]
    while True:
        task = store.client.tasks.get(task_id=task_id)
        if task.get("completed"):
            break
        time.sleep(poll_seconds)
    response = task.get("response") or {}
    if task.get("error") or response.get("failures"):
        raise RuntimeError(
            f"update_by_query task {task_id} failed: "
            f"{task.get('error') or response.get('failures')}"
        )
    if response.get("version_conflicts"):
        # Events changed meanwhile (live writes, erasure) were skipped: a rerun completes them.
        logger.warning(
            "[KPI][BACKFILL] %d event(s) skipped on version conflict, rerun to complete",
            response["version_conflicts"],
        )
    return int(response.get("updated", 0))


def reindex_turns(
    store: OpenSearchKPIStore,
    since: datetime | None,
    *,
    dry_run: bool,
    poll_seconds: float = 5.0,
) -> int:
    """No-op rewrite of turn events so fields mapped after indexing are searchable."""
    query = {
        "bool": {
            "filter": [{"term": {"metric.name": TURN_METRIC}}, *_since_filter(since)]
        }
    }
    if dry_run:
        return int(
            store.client.count(index=store.index, body={"query": query})["count"]
        )
    return run_update_by_query(store, {"query": query}, poll_seconds)


async def attribute_teams(
    store: OpenSearchKPIStore,
    engine: AsyncEngine,
    rebac: RebacEngine,
    since: datetime | None,
    *,
    dry_run: bool,
    poll_seconds: float = 1.0,
) -> dict[str, int]:
    """Set `dims.team_id` on past human API events that lack it."""
    sessions = await load_user_sessions(engine, since)
    totals = {"users": 0, "users_without_team": 0, "events": 0}
    for user_id, event_count in list(users_missing_team(store, since)):
        totals["users"] += 1
        user_sessions = sessions.get(user_id) or UserSessions()
        days = day_to_team(user_sessions)
        fallback = fallback_team(user_sessions, await member_teams(rebac, user_id))
        if not days and fallback is None:
            totals["users_without_team"] += 1
            logger.debug("[KPI][BACKFILL] no team for user_id=%s", user_id)
            continue
        if dry_run:
            totals["events"] += event_count
            continue
        body = {
            "query": _missing_team_query(since, user_id),
            "script": {
                "lang": "painless",
                "source": TEAM_SCRIPT,
                "params": {"days": days, "fallback": fallback},
            },
        }
        totals["events"] += run_update_by_query(store, body, poll_seconds)
    if not dry_run and totals["events"]:
        store.client.indices.refresh(index=store.index)
    return totals


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fred-control-plane-kpi-backfill",
        description="Complete past KPI events (reindex turns, attribute API requests to teams).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count the events to update, change none.",
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        default=None,
        help="Only events at or after this ISO date/time (default: all).",
    )
    parser.add_argument("--step", choices=("reindex", "teams", "all"), default="all")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from control_plane_backend.app.container import build_application_container
    from control_plane_backend.config.loader import load_configuration

    container = build_application_container(load_configuration())
    store = container.get_kpi_store()
    if store is None:
        logger.error("[KPI][BACKFILL] no OpenSearch KPI store configured")
        return 2
    verb = "would update" if args.dry_run else "updated"
    if args.step in ("reindex", "all"):
        count = reindex_turns(store, args.since, dry_run=args.dry_run)
        logger.info("[KPI][BACKFILL] reindex: %s %d turn event(s)", verb, count)
    if args.step in ("teams", "all"):
        engine = container.get_pg_async_engine()
        try:
            totals = await attribute_teams(
                store,
                engine,
                container.get_rebac_engine(),
                args.since,
                dry_run=args.dry_run,
            )
        finally:
            await engine.dispose()
        logger.info(
            "[KPI][BACKFILL] teams: %s %d event(s) for %d user(s), %d user(s) without team",
            verb,
            totals["events"],
            totals["users"] - totals["users_without_team"],
            totals["users_without_team"],
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
