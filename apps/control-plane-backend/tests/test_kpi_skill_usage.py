# Copyright Thales 2026. Licensed under the Apache License, Version 2.0.
from datetime import datetime, timezone
from threading import get_ident
from types import SimpleNamespace
from typing import cast

import pytest
from control_plane_backend.kpi.presets.skill_usage import (
    query_skill_usage,
    query_user_skill_usage,
)
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", [None, TeamId("team-1")])
async def test_skill_usage_scope_counts_limit_and_thread_offload(team_id):
    body_seen = []
    loop_thread = get_ident()

    def search(*, index, body):
        assert get_ident() != loop_thread
        assert index == "owned-test-index"
        body_seen.append(body)
        return {
            "aggregations": {
                "skills": {
                    "sum_other_doc_count": 3,
                    "buckets": [
                        {
                            "key": "a",
                            "origins": {
                                "buckets": {
                                    "user": {"doc_count": 4},
                                    "agent": {"doc_count": 2},
                                }
                            },
                        },
                        {
                            "key": "b",
                            "origins": {"buckets": {"agent": {"doc_count": 1}}},
                        },
                    ],
                }
            }
        }

    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    until = datetime(2026, 10, 7, tzinfo=timezone.utc)
    result = await query_skill_usage(
        cast(
            OpenSearchKPIStore,
            SimpleNamespace(
                client=SimpleNamespace(search=search), index="owned-test-index"
            ),
        ),
        user=KeycloakUser(uid="u", username="u", roles=[]),
        since=since,
        until=until,
        request=Request({"type": "http"}),
        team_id=team_id,
    )
    assert [row.model_dump() for row in result.rows] == [
        {"skill_name": "a", "user_count": 4, "model_count": 2, "total": 6},
        {"skill_name": "b", "user_count": 0, "model_count": 1, "total": 1},
    ]
    assert result.truncated and result.since == since and result.until == until
    filters = body_seen[0]["query"]["bool"]["filter"]
    assert {"term": {"metric.name": "agent.skill_loaded_total"}} in filters
    assert {
        "range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}
    } in filters
    assert ({"term": {"dims.team_id": "team-1"}} in filters) == (team_id is not None)
    assert body_seen[0]["aggs"]["skills"]["terms"] == {
        "field": "dims.skill_name",
        "size": 100,
        "order": [{"_count": "desc"}, {"_key": "asc"}],
    }


@pytest.mark.asyncio
async def test_skill_usage_empty_and_router_authorization(monkeypatch):
    from unittest.mock import AsyncMock

    from control_plane_backend.kpi import api
    from control_plane_backend.kpi.scope import KpiScope
    from fred_core.security.models import AuthorizationError, Resource

    scope = AsyncMock(return_value=KpiScope(team_id=TeamId("team-1")))
    monkeypatch.setattr(api, "resolve_kpi_scope", scope)
    route = next(
        r
        for r in api.build_kpi_router().routes
        if isinstance(r, APIRoute) and r.path.endswith("/skill_usage")
    )
    store = SimpleNamespace(
        client=SimpleNamespace(
            search=lambda **kwargs: {"aggregations": {"skills": {"buckets": []}}}
        ),
        index="test",
    )
    user = KeycloakUser(uid="u", username="u", roles=[])
    request = Request({"type": "http"})
    response = await route.endpoint(
        request=request,
        since=None,
        until=None,
        team_id=TeamId("team-1"),
        user=user,
        store=store,
    )
    assert response.rows == [] and response.truncated is False
    scope.assert_awaited_once_with(
        request, user, TeamId("team-1"), platform_admin_only=False, self_scoped=False
    )
    scope.side_effect = AuthorizationError(
        "u", "can_observe_platform", Resource.ORGANIZATION
    )
    with pytest.raises(AuthorizationError):
        await route.endpoint(
            request=request,
            since=None,
            until=None,
            team_id=None,
            user=user,
            store=store,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["user-a", "user-b"])
async def test_personal_skill_query_filters_authenticated_user_and_both_origins(uid):
    seen = []

    def search(**kwargs):
        seen.append(kwargs["body"])
        return {"aggregations": {"skills": {"buckets": []}}}

    store = cast(
        OpenSearchKPIStore,
        SimpleNamespace(client=SimpleNamespace(search=search), index="test"),
    )
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    until = datetime(2026, 10, 7, tzinfo=timezone.utc)
    await query_user_skill_usage(
        store,
        user=KeycloakUser(uid=uid, username=uid, roles=[]),
        since=since,
        until=until,
        request=Request({"type": "http"}),
    )
    filters = seen[0]["query"]["bool"]["filter"]
    assert {"term": {"dims.user_id": uid}} in filters
    assert {"terms": {"dims.skill_origin": ["user", "agent"]}} in filters
    assert not any("dims.team_id" in f.get("term", {}) for f in filters)
    assert {
        "range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}
    } in filters


@pytest.mark.asyncio
async def test_personal_skill_route_is_self_scoped_and_rejects_team(monkeypatch):
    from unittest.mock import AsyncMock

    from control_plane_backend.kpi import api
    from control_plane_backend.kpi.scope import KpiScope

    scope = AsyncMock(return_value=KpiScope(team_id=None))
    monkeypatch.setattr(api, "resolve_kpi_scope", scope)
    route = next(
        r
        for r in api.build_kpi_router().routes
        if isinstance(r, APIRoute) and r.path.endswith("/user_skill_usage")
    )
    seen = []

    def search(**kwargs):
        seen.append(kwargs["body"])
        return {"aggregations": {"skills": {"buckets": []}}}

    store = SimpleNamespace(client=SimpleNamespace(search=search), index="test")
    user = KeycloakUser(uid="authenticated-user", username="u", roles=[])
    request = Request({"type": "http"})
    await route.endpoint(
        request=request, since=None, until=None, team_id=None, user=user, store=store
    )
    scope.assert_awaited_once_with(
        request, user, None, platform_admin_only=False, self_scoped=True
    )
    assert {"term": {"dims.user_id": user.uid}} in seen[0]["query"]["bool"]["filter"]
    with pytest.raises(HTTPException) as exc:
        await route.endpoint(
            request=request,
            since=None,
            until=None,
            team_id=TeamId("other-team"),
            user=user,
            store=store,
        )
    assert exc.value.status_code == 400
    assert len(seen) == 1
