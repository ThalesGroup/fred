# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Build the operator's catalog from safe, consent-scoped SQL projections."""

from datetime import datetime
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
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
    incident_exchange = Grant.incident["cutoff"]["exchange_id"].as_string()
    incident_error_ref = Grant.incident["support_error_ref"].as_string()
    incident_category = Grant.incident["failure_category"].as_string()
    same_incident = incident_exchange == Turn.exchange_id
    captured = (
        select(
            Turn.session_id,
            Turn.agent_display_name,
            Turn.started_at,
            Turn.capture_id.label("entry_id"),
            Turn.history_rank,
            case((same_incident, TraceOutcome.FAILED.value), else_=Turn.outcome).label(
                "outcome"
            ),
            func.coalesce(
                case((same_incident, incident_category)), Turn.failure_category
            ).label("failure_category"),
            Turn.completed_at,
            Turn.http_availability,
            literal(False).label("history_only"),
            func.coalesce(
                Turn.support_error_ref, case((same_incident, incident_error_ref))
            ).label("support_error_ref"),
        )
        .select_from(Turn)
        .join(owners, owners.c.session_id == Turn.session_id)
        .outerjoin(
            Grant, and_(Grant.session_id == Turn.session_id, Grant.revoked_at.is_(None))
        )
    )
    matching_capture = aliased(Turn)
    has_matching_capture = (
        select(matching_capture.capture_id)
        .where(
            matching_capture.session_id == Grant.session_id,
            or_(
                Grant.incident.is_(None),
                matching_capture.exchange_id == incident_exchange,
            ),
        )
        .exists()
    )
    history_only = (
        select(
            Grant.session_id,
            literal(""),
            func.coalesce(Grant.diagnostic_at, Grant.started_at),
            Grant.grant_id,
            func.coalesce(
                Grant.incident["cutoff"]["first_rank"].as_integer(), Grant.first_rank
            ),
            case(
                (Grant.incident.is_not(None), TraceOutcome.FAILED.value),
                else_=TraceOutcome.UNKNOWN.value,
            ),
            incident_category,
            Grant.granted_at,
            literal(None),
            literal(True),
            incident_error_ref,
        )
        .select_from(Grant)
        .join(owners, owners.c.session_id == Grant.session_id)
        .where(Grant.revoked_at.is_(None), ~has_matching_capture)
    )
    return union_all(captured, history_only).cte("trace_events")


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


def _user_match(postgres: bool):
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


async def catalog_rows(
    session: AsyncSession,
    filters: TraceCatalogFilters,
    *,
    postgres: bool,
    local_content_access: bool,
    limit: int,
    cursor: str | None,
    before: tuple[datetime, str] | None,
) -> list[Any]:
    owners_query = select(Owner.session_id).where(*_visible_owner())
    if filters.team_ids:
        owners_query = owners_query.where(Owner.team_id.in_(filters.team_ids))
    owners = owners_query.cte("trace_owners")
    events = _catalog_events(owners)
    ranked = select(
        events,
        func.row_number()
        .over(
            partition_by=events.c.session_id,
            order_by=(
                case((events.c.outcome == TraceOutcome.FAILED.value, 0), else_=1),
                events.c.history_rank.desc(),
                events.c.entry_id.desc(),
            ),
        )
        .label("representative"),
        func.max(events.c.started_at)
        .over(partition_by=events.c.session_id)
        .label("latest_started_at"),
        func.max(case((_matching_failure(events, filters), 1), else_=0))
        .over(partition_by=events.c.session_id)
        .label("matches_failure"),
    ).subquery()
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
    sort_key = {
        TraceCatalogSort.LATEST: ranked.c.latest_started_at,
        TraceCatalogSort.TITLE: func.lower(func.coalesce(title, "")),
        TraceCatalogSort.USER: func.lower(
            func.coalesce(UserRow.username, Owner.user_id, "")
        ),
        TraceCatalogSort.TEAM: func.lower(team_name),
        TraceCatalogSort.OUTCOME: func.coalesce(
            ranked.c.failure_category, ranked.c.outcome
        ),
        TraceCatalogSort.CONSENT: access,
    }[filters.sort]
    filtered = (
        select(
            ranked,
            title.label("title"),
            agent_name.label("display_name"),
            Owner.user_id,
            UserRow.username,
            Owner.team_id,
            team_name.label("team_name"),
            access.label("access"),
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
        .outerjoin(UserRow, _user_match(postgres))
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
            outcome.value
            for outcome in filters.outcomes
            if isinstance(outcome, TraceOutcome) and outcome != TraceOutcome.FAILED
        ]
        filtered = filtered.where(
            or_(ranked.c.outcome.in_(states), ranked.c.matches_failure == 1)
        )
    elif filters.failed_only:
        filtered = filtered.where(ranked.c.outcome == TraceOutcome.FAILED.value)
    if filters.since is not None:
        filtered = filtered.where(ranked.c.latest_started_at >= filters.since)
    if filters.until is not None:
        filtered = filtered.where(ranked.c.latest_started_at <= filters.until)
    query = filters.query.strip()
    if query:
        search = query.lower()
        fields = (
            ranked.c.session_id,
            title,
            agent_name,
            Owner.user_id,
            UserRow.username,
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
                error_match,
                Grant.incident["support_error_ref"].as_string() == search,
            )
        )
    entries = filtered.cte("trace_catalog")
    asc = filters.direction == "asc"
    result = select(entries)
    if cursor is not None:
        anchor = (
            select(entries.c.sort_key)
            .where(entries.c.session_id == cursor)
            .scalar_subquery()
        )
        key_after = entries.c.sort_key > anchor if asc else entries.c.sort_key < anchor
        id_after = (
            entries.c.session_id > cursor if asc else entries.c.session_id < cursor
        )
        result = result.where(
            or_(key_after, and_(entries.c.sort_key == anchor, id_after))
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
    return list(await session.execute(result.limit(limit + 1)))
