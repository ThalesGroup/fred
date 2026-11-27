# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Build the operator's catalog from safe, consent-scoped SQL projections."""

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Any

from fred_core.conversation_trace import TraceOutcome
from fred_core.history.history_schema import TraceFailureCategory
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from sqlalchemy import (
    String,
    Uuid,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.conversation_traces.schemas import (
    TraceCatalogFilters,
    TraceCatalogSort,
    TraceConsentFilter,
    TraceContentAccess,
    TraceTeamOption,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow as Grant,
)
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceIncidentRow as Incident,
)
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceTurnRow as Turn,
)
from control_plane_backend.models.session_metadata_models import (
    SessionMetadataRow as Owner,
)


def _visible_owner():
    return (
        or_(Owner.deleted_at.is_(None), Owner.trace_retained_after_delete.is_(True)),
        Owner.trace_erasing.is_(False),
    )


def _active_grant():
    return and_(Grant.session_id == Owner.session_id, Grant.revoked_at.is_(None))


class StaleTraceCursor(Exception):
    pass


def cursor_revision(row: Mapping[str, Any], sort: TraceCatalogSort) -> str:
    # Title revisions are independent of their text, including when masked.
    sort_key = None if sort == TraceCatalogSort.TITLE else row["sort_key"]
    state = (
        row["session_id"],
        row["entry_id"],
        row["latest_started_at"],
        row["title_revision"] if sort == TraceCatalogSort.TITLE else None,
        row["grant_id"],
        row["access"],
        sort_key,
    )
    return sha256(repr(state).encode()).hexdigest()[:32]


async def list_catalog_teams(session: AsyncSession) -> list[TraceTeamOption]:
    rows = await session.execute(
        select(
            Owner.team_id,
            func.coalesce(TeamMetadataRow.name, Owner.team_id).label("team_name"),
        )
        .outerjoin(TeamMetadataRow, TeamMetadataRow.id == Owner.team_id)
        .where(
            *_visible_owner(),
            or_(
                select(Turn.capture_id)
                .where(Turn.session_id == Owner.session_id)
                .exists(),
                select(Grant.grant_id).where(_active_grant()).exists(),
            ),
        )
        .distinct()
        .order_by("team_name", Owner.team_id)
    )
    return [TraceTeamOption(team_id=team_id, name=name) for team_id, name in rows]


def _catalog_events(owners):
    captured = (
        select(
            Turn.session_id,
            Turn.agent_display_name,
            Turn.started_at,
            Turn.capture_id.label("entry_id"),
            Turn.history_rank,
            Turn.outcome,
            Turn.failure_category,
            Turn.completed_at,
            Turn.http_availability,
            literal(False).label("history_only"),
            Turn.support_error_ref,
            literal(-1).label("report_rank"),
        )
        .select_from(Turn)
        .join(owners, owners.c.session_id == Turn.session_id)
        .where(
            ~select(Incident.support_error_ref)
            .join(
                Grant,
                and_(
                    Grant.session_id == Incident.session_id, Grant.revoked_at.is_(None)
                ),
            )
            .where(
                Incident.session_id == Turn.session_id,
                Incident.exchange_id == Turn.exchange_id,
                or_(
                    Turn.support_error_ref.is_(None),
                    Incident.support_error_ref == Turn.support_error_ref,
                ),
            )
            .correlate(Turn)
            .exists()
        )
    )
    reported = (
        select(
            Incident.session_id,
            func.coalesce(Turn.agent_display_name, ""),
            func.coalesce(Turn.started_at, Incident.started_at),
            Incident.support_error_ref,
            Incident.first_rank,
            literal(TraceOutcome.FAILED.value),
            func.coalesce(Incident.failure_category, Turn.failure_category),
            case(
                (Turn.capture_id.is_(None), Grant.granted_at), else_=Turn.completed_at
            ),
            Turn.http_availability,
            Turn.capture_id.is_(None),
            Incident.support_error_ref,
            Incident.last_rank,
        )
        .select_from(Incident)
        .join(owners, owners.c.session_id == Incident.session_id)
        .join(
            Grant,
            and_(Grant.session_id == Incident.session_id, Grant.revoked_at.is_(None)),
        )
        .outerjoin(
            Turn,
            and_(
                Turn.session_id == Incident.session_id,
                Turn.exchange_id == Incident.exchange_id,
            ),
        )
    )
    history_only = (
        select(
            Grant.session_id,
            literal(""),
            func.coalesce(Grant.diagnostic_at, Grant.started_at),
            Grant.grant_id,
            Grant.first_rank,
            literal(TraceOutcome.UNKNOWN.value),
            literal(None),
            Grant.granted_at,
            literal(None),
            literal(True),
            literal(None),
            literal(-1),
        )
        .select_from(Grant)
        .join(owners, owners.c.session_id == Grant.session_id)
        .where(
            Grant.revoked_at.is_(None),
            ~select(Turn.capture_id)
            .where(Turn.session_id == Grant.session_id)
            .exists(),
            ~select(Incident.support_error_ref)
            .where(Incident.session_id == Grant.session_id)
            .exists(),
        )
    )
    return union_all(captured, reported, history_only).cte("trace_events")


def _matching_failure(events, filters: TraceCatalogFilters):
    outcomes = filters.outcomes
    categories = [
        outcome.value
        for outcome in outcomes
        if isinstance(outcome, TraceFailureCategory)
    ]
    kinds = [events.c.failure_category.in_(categories)]
    if TraceOutcome.FAILED in outcomes:
        kinds.append(events.c.failure_category.is_(None))
    return and_(events.c.outcome == TraceOutcome.FAILED.value, or_(*kinds))


def trace_user_match(postgres: bool):
    if postgres:
        # Invalid legacy identifiers never reach PostgreSQL's UUID input function.
        candidate = case(
            (
                Owner.user_id.op("~*")(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
                ),
                cast(Owner.user_id, Uuid),
            ),
        )
        return UserRow.id == candidate
    return cast(UserRow.id, String) == func.replace(Owner.user_id, "-", "")


def _trace_user_full_name():
    return func.trim(
        func.coalesce(func.trim(UserRow.first_name), "")
        + " "
        + func.coalesce(func.trim(UserRow.last_name), "")
    )


def trace_user_display_name():
    return func.coalesce(func.nullif(_trace_user_full_name(), ""), UserRow.username)


async def catalog_rows(
    session: AsyncSession,
    filters: TraceCatalogFilters,
    *,
    postgres: bool,
    local_content_access: bool,
    limit: int,
    cursor: str | None,
    expected_revision: str | None,
    before: tuple[datetime, str] | None,
) -> list[Any]:
    owners_query = select(Owner.session_id).where(*_visible_owner())
    if filters.team_ids:
        owners_query = owners_query.where(Owner.team_id.in_(filters.team_ids))
    owners = owners_query.cte("trace_owners")
    events = _catalog_events(owners)
    search = filters.query.strip().lower()
    query_outcomes = [
        item.value if isinstance(item, (TraceOutcome, TraceFailureCategory)) else item
        for item in filters.query_outcomes
    ]
    ranked_query = select(
        events,
        func.row_number()
        .over(
            partition_by=events.c.session_id,
            order_by=(
                case((events.c.outcome == TraceOutcome.FAILED.value, 0), else_=1),
                events.c.history_rank.desc(),
                events.c.report_rank.desc(),
                events.c.entry_id.desc(),
            ),
        )
        .label("representative"),
        func.max(events.c.started_at)
        .over(partition_by=events.c.session_id)
        .label("latest_started_at"),
        func.count().over(partition_by=events.c.session_id).label("event_count"),
        func.max(case((_matching_failure(events, filters), 1), else_=0))
        .over(partition_by=events.c.session_id)
        .label("matches_failure"),
    )
    if search:
        event_outcome = func.coalesce(events.c.failure_category, events.c.outcome)
        outcome_matches = or_(
            func.lower(event_outcome).contains(search, autoescape=True),
            event_outcome.in_(query_outcomes),
        )
        ranked_query = ranked_query.add_columns(
            func.max(
                case(
                    (
                        and_(
                            events.c.outcome == TraceOutcome.FAILED.value,
                            outcome_matches,
                        ),
                        1,
                    ),
                    else_=0,
                )
            )
            .over(partition_by=events.c.session_id)
            .label("matches_failure_query"),
        )
    ranked = ranked_query.subquery()
    is_local = literal(local_content_access) & Owner.trace_retained_after_delete.is_(
        False
    )
    is_shared = Grant.grant_id.is_not(None)
    title = case(
        (
            or_(
                is_local, and_(is_shared, Owner.title_revision == Grant.title_revision)
            ),
            Owner.title,
        )
    )
    access = case(
        (is_local, TraceContentAccess.LOCAL.value),
        (is_shared, TraceContentAccess.SHARED.value),
        else_=TraceContentAccess.MASKED.value,
    )
    agent_name = func.coalesce(
        AgentInstanceRow.display_name,
        Owner.agent_display_name,
        ranked.c.agent_display_name,
    )
    team_name = func.coalesce(TeamMetadataRow.name, Owner.team_id)
    user_name = func.coalesce(trace_user_display_name(), Owner.user_id)
    catalog_outcome = case(
        (
            and_(
                ranked.c.event_count == 1,
                ranked.c.history_rank == 0,
                ranked.c.outcome == TraceOutcome.UNKNOWN.value,
                ranked.c.completed_at.is_(None),
                ~ranked.c.history_only,
            ),
            "in_progress",
        ),
        else_=ranked.c.outcome,
    ).label("catalog_outcome")
    outcome = func.coalesce(ranked.c.failure_category, catalog_outcome)
    sort_key = {
        TraceCatalogSort.LATEST: ranked.c.latest_started_at,
        TraceCatalogSort.TITLE: func.lower(func.coalesce(title, "")),
        TraceCatalogSort.USER: func.lower(func.coalesce(user_name, "")),
        TraceCatalogSort.TEAM: func.lower(team_name),
        TraceCatalogSort.OUTCOME: outcome,
        TraceCatalogSort.CONSENT: access,
    }[filters.sort]
    filtered = (
        select(
            ranked,
            catalog_outcome,
            title.label("title"),
            agent_name.label("display_name"),
            Owner.user_id,
            UserRow.username,
            user_name.label("user_display_name"),
            Owner.team_id,
            team_name.label("team_name"),
            access.label("access"),
            case((title.is_not(None), Owner.title_revision)).label("title_revision"),
            Grant.grant_id,
            sort_key.label("sort_key"),
        )
        .select_from(ranked)
        .join(Owner, Owner.session_id == ranked.c.session_id)
        .outerjoin(Grant, _active_grant())
        .outerjoin(
            AgentInstanceRow,
            and_(
                AgentInstanceRow.agent_instance_id == Owner.agent_instance_id,
                AgentInstanceRow.team_id == Owner.team_id,
            ),
        )
        .outerjoin(TeamMetadataRow, TeamMetadataRow.id == Owner.team_id)
        .outerjoin(UserRow, trace_user_match(postgres))
        .where(ranked.c.representative == 1)
    )
    if filters.user_id is not None:
        filtered = filtered.where(
            or_(
                Owner.user_id == filters.user_id,
                func.lower(UserRow.username) == filters.user_id.lower(),
            )
        )
    if filters.consent == TraceConsentFilter.SHARED:
        filtered = filtered.where(is_shared)
    elif filters.consent == TraceConsentFilter.MASKED:
        filtered = filtered.where(access == TraceContentAccess.MASKED.value)
    if filters.outcomes:
        states = [
            str(state)
            for state in filters.outcomes
            if not isinstance(state, TraceFailureCategory)
            and state != TraceOutcome.FAILED
        ]
        filtered = filtered.where(
            or_(catalog_outcome.in_(states), ranked.c.matches_failure == 1)
        )
    elif filters.failed_only:
        filtered = filtered.where(ranked.c.outcome == TraceOutcome.FAILED.value)
    if filters.since is not None:
        filtered = filtered.where(ranked.c.latest_started_at >= filters.since)
    if filters.until is not None:
        filtered = filtered.where(ranked.c.latest_started_at <= filters.until)
    if search:
        fields = (
            ranked.c.session_id,
            title,
            agent_name,
            Owner.agent_instance_id,
            Owner.user_id,
            UserRow.username,
            _trace_user_full_name(),
            team_name,
        )
        error_match = (
            select(Turn.capture_id)
            .where(
                Turn.session_id == Owner.session_id, Turn.support_error_ref == search
            )
            .correlate(Owner)
            .exists()
        )
        filtered = filtered.where(
            or_(
                *(
                    func.lower(field).contains(search, autoescape=True)
                    for field in fields
                ),
                func.lower(outcome).contains(search, autoescape=True),
                outcome.in_(query_outcomes),
                ranked.c.matches_failure_query == 1,
                error_match,
                select(Incident.support_error_ref)
                .where(
                    Incident.session_id == Owner.session_id,
                    Incident.support_error_ref == search,
                    is_shared,
                )
                .correlate(Owner, Grant)
                .exists(),
            )
        )
    entries = filtered.cte("trace_catalog")
    asc = filters.direction == "asc"
    result = select(entries)
    anchor = None
    if cursor is not None:
        anchor = (
            select(entries).where(entries.c.session_id == cursor).cte("trace_anchor")
        )
        key_after = (
            entries.c.sort_key > anchor.c.sort_key
            if asc
            else entries.c.sort_key < anchor.c.sort_key
        )
        id_after = (
            entries.c.session_id > cursor if asc else entries.c.session_id < cursor
        )
        result = result.join(anchor, literal(True)).where(
            or_(key_after, and_(entries.c.sort_key == anchor.c.sort_key, id_after))
        )
    elif before is not None:
        date, entry_id = before
        result = result.where(
            or_(
                entries.c.latest_started_at < date,
                and_(
                    entries.c.latest_started_at == date, entries.c.entry_id < entry_id
                ),
            )
        )
    key = entries.c.sort_key
    tie = entries.c.session_id
    result = (
        result.order_by(key.asc(), tie.asc())
        if asc
        else result.order_by(key.desc(), tie.desc())
    )
    result = result.limit(limit + 1)
    page = result.cte("trace_page")
    # Aggregate distinct failures only for the bounded page, in the same snapshot.
    failure = distinct(
        func.coalesce(events.c.failure_category, TraceOutcome.FAILED.value)
    )
    aggregate = (
        func.string_agg(failure, ",") if postgres else func.group_concat(failure)
    )
    page_failures = (
        select(events.c.session_id, aggregate.label("failure_outcomes"))
        .join(page, page.c.session_id == events.c.session_id)
        .where(events.c.outcome == TraceOutcome.FAILED.value)
        .group_by(events.c.session_id)
        .subquery()
    )
    failure_join = page.c.session_id == page_failures.c.session_id
    order = (page.c.sort_key, page.c.session_id)
    page_order = [column.asc() if asc else column.desc() for column in order]
    if anchor is None:
        return list(
            await session.execute(
                select(page, page_failures.c.failure_outcomes)
                .select_from(page.outerjoin(page_failures, failure_join))
                .order_by(*page_order)
            )
        )
    # The anchor and page must come from the same snapshot. Retain an anchor
    # row even for a valid empty page so deletion is distinguishable.
    revision_columns = (
        "session_id",
        "entry_id",
        "latest_started_at",
        "title_revision",
        "grant_id",
        "access",
        "sort_key",
    )
    anchored_page = select(
        page,
        page_failures.c.failure_outcomes,
        *(anchor.c[name].label(f"anchor_{name}") for name in revision_columns),
    ).select_from(
        anchor.outerjoin(page, literal(True)).outerjoin(page_failures, failure_join)
    )
    rows = list(await session.execute(anchored_page.order_by(*page_order)))
    if not rows:
        raise StaleTraceCursor()
    state = {name: rows[0]._mapping[f"anchor_{name}"] for name in revision_columns}
    if expected_revision is not None and expected_revision != cursor_revision(
        state, filters.sort
    ):
        raise StaleTraceCursor()
    return rows if rows[0].session_id is not None else []
