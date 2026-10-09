# Copyright Thales 2026. Licensed under the Apache License, Version 2.0.
"""Successful skill loads by name and trusted invocation origin."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import SkillUsageResponse, SkillUsageRow

TOP_SKILLS = 100


async def query_skill_usage(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
    team_id: TeamId | None = None,
) -> SkillUsageResponse:
    # The preset router owns authorization for both team and platform scope.
    del user, request
    filters: list[dict[str, Any]] = []
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})
    return await _query_skill_usage(
        store, since=since, until=until, scope_filters=filters
    )


async def query_user_skill_usage(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> SkillUsageResponse:
    del request
    return await _query_skill_usage(
        store,
        since=since,
        until=until,
        scope_filters=[{"term": {"dims.user_id": user.uid}}],
    )


async def _query_skill_usage(
    store: OpenSearchKPIStore,
    *,
    since: datetime,
    until: datetime,
    scope_filters: list[dict[str, Any]],
) -> SkillUsageResponse:
    filters: list[dict[str, Any]] = [
        {"term": {"metric.name": "agent.skill_loaded_total"}},
        {"terms": {"dims.skill_origin": ["user", "agent"]}},
        {"range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}},
        *scope_filters,
    ]
    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "skills": {
                "terms": {
                    "field": "dims.skill_name",
                    "size": TOP_SKILLS,
                    "order": [{"_count": "desc"}, {"_key": "asc"}],
                },
                "aggs": {
                    "origins": {
                        "filters": {
                            "filters": {
                                "user": {"term": {"dims.skill_origin": "user"}},
                                "agent": {"term": {"dims.skill_origin": "agent"}},
                            }
                        }
                    }
                },
            }
        },
    }
    response = await asyncio.to_thread(
        store.client.search, index=store.index, body=body
    )
    skills = response.get("aggregations", {}).get("skills", {})
    rows = []
    for bucket in skills.get("buckets", []):
        origins = bucket.get("origins", {}).get("buckets", {})
        user_count = int(origins.get("user", {}).get("doc_count", 0))
        model_count = int(origins.get("agent", {}).get("doc_count", 0))
        rows.append(
            SkillUsageRow(
                skill_name=bucket["key"],
                user_count=user_count,
                model_count=model_count,
                total=user_count + model_count,
            )
        )
    return SkillUsageResponse(
        rows=rows,
        since=since,
        until=until,
        truncated=skills.get("sum_other_doc_count", 0) > 0,
    )


SKILL_USAGE_PRESET = PresetDef(
    name="skill_usage",
    response_model=SkillUsageResponse,
    handler=query_skill_usage,
    summary="Successful skill loads by user or model over the selected time range",
    team_scopable=True,
)


USER_SKILL_USAGE_PRESET = PresetDef(
    name="user_skill_usage",
    response_model=SkillUsageResponse,
    handler=query_user_skill_usage,
    summary="The requesting user's successful skill loads by user or model",
    self_scoped=True,
)
