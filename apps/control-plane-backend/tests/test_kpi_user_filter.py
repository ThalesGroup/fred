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

"""User filter of the platform analytics: parsing, matching on stored access
attributes, coverage counts, authorization, cache, and the clause every
user-filterable preset must add to each of its searches."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from _kpi_test_doubles import SINCE, UNTIL, USER, FakeKpiStore, stub_side_reads
from control_plane_backend.kpi import api
from control_plane_backend.kpi import scope as kpi_scope
from control_plane_backend.kpi import user_filter as uf
from control_plane_backend.kpi.presets import (
    PRESETS,
)
from control_plane_backend.kpi.scope import KpiScope, resolve_kpi_scope
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from fred_core import ORGANIZATION_ID, OrganizationPermission, TeamPermission
from fred_core.common import TeamId
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.platform_access.rules import path_key
from fred_pod.security.platform_access import PlatformAccessPolicy

ORG = path_key(["organisation"])
UNIT = path_key(["profile", "unit"])
ROWS: list[tuple[str, Any]] = [
    ("u1", {ORG: "Acme", UNIT: ["R&D", "Lab"]}),
    ("u2", {ORG: "acme", UNIT: "Sales"}),
    ("u3", {ORG: "Other"}),
    ("u4", {ORG: None}),
    ("u5", None),
]


def _filter(*conditions: dict[str, Any], combination: str = "all") -> Any:
    return uf.AnalyticsUserFilter.model_validate(
        {"combination": combination, "conditions": list(conditions)}
    )


def _org(operator: str, value: str, **extra: Any) -> dict[str, Any]:
    return {"claim": ["organisation"], "operator": operator, "value": value, **extra}


def _unit(operator: str, value: str) -> dict[str, Any]:
    return {"claim": ["profile", "unit"], "operator": operator, "value": value}


@pytest.mark.parametrize(
    ("condition", "matched", "no_data"),
    [
        (_org("equals", "acme"), ("u1", "u2"), 2),
        (_org("equals", "acme", case_sensitive=True), ("u2",), 2),
        (_org("not_equals", "acme"), ("u3",), 2),
        (_org("contains", "th"), ("u3",), 2),
        (_org("not_contains", "c"), ("u3",), 2),
        (_org("regex", "a.*e"), ("u1", "u2"), 2),
        # A list matches when one of its items does.
        (_unit("equals", "lab"), ("u1",), 3),
        (_unit("not_contains", "a"), (), 3),
    ],
)
def test_operators_and_no_data(
    condition: dict[str, Any], matched: tuple[str, ...], no_data: int
) -> None:
    result = uf.match_users(_filter(condition), ROWS)
    assert result.user_ids == matched
    # Users without a stored value are never matched, negated operators included.
    assert result.no_data == no_data
    assert result.known_users == len(ROWS)


def test_all_and_any() -> None:
    both = (_org("equals", "acme"), _unit("contains", "sal"))
    assert uf.match_users(_filter(*both), ROWS).user_ids == ("u2",)
    any_of = uf.match_users(_filter(*both, combination="any"), ROWS)
    assert any_of.user_ids == ("u1", "u2")
    # u3 lacks the unit and matches nothing else: no data, like u4 and u5.
    assert any_of.no_data == 3


def test_regex_timeout_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        uf, "evaluate", lambda *a: SimpleNamespace(matched=False, reasons=["timeout"])
    )
    with pytest.raises(HTTPException) as exc:
        uf.match_users(_filter(_org("regex", "(a+)+$")), ROWS)
    assert exc.value.status_code == 400


def test_scan_budget_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uf, "SCAN_BUDGET_SECONDS", -1.0)
    with pytest.raises(HTTPException) as exc:
        uf.match_users(_filter(_org("equals", "acme")), ROWS)
    assert exc.value.status_code == 400


def test_too_many_matches_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uf, "MAX_MATCHED_USERS", 1)
    with pytest.raises(HTTPException) as exc:
        uf.match_users(_filter(_org("equals", "acme")), ROWS)
    assert exc.value.status_code == 400
    assert "narrow" in str(exc.value.detail)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"conditions": []}),
        json.dumps({"mode": "block", "conditions": [_org("equals", "a")]}),
        json.dumps({"conditions": [_org("equals", "a")] * (uf.MAX_CONDITIONS + 1)}),
        json.dumps({"conditions": [_org("regex", "(")]}),
        "x" * (uf.MAX_PARAM_LENGTH + 1),
    ],
)
def test_invalid_filters_are_refused(raw: str) -> None:
    with pytest.raises(HTTPException) as exc:
        uf.parse_user_filter(raw)
    assert exc.value.status_code == 400


def test_parse_and_canonical_form() -> None:
    assert uf.parse_user_filter(None) is None and uf.parse_user_filter(" ") is None
    parsed = uf.parse_user_filter(json.dumps({"conditions": [_org("equals", "A")]}))
    assert parsed is not None
    same = _filter(_org("equals", "A", case_sensitive=False))
    assert parsed.canonical() == same.canonical()


def test_stored_fields_list_rule_paths_first_with_their_coverage() -> None:
    policy = PlatformAccessPolicy.model_validate(
        {"conditions": [_org("equals", "x"), {**_org("equals", "x"), "claim": ["new"]}]}
    )
    fields = uf.stored_fields(ROWS, policy)
    assert [(f.claim, f.users, f.in_rule) for f in fields] == [
        (["organisation"], 3, True),
        (["new"], 0, True),
        (["profile", "unit"], 2, False),
    ]


# --- resolution cache ---------------------------------------------------------


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    env: dict[str, Any] = {"revision": 1, "scans": 0}
    uf._cache.clear()

    class _Access:
        async def state(self) -> Any:
            return SimpleNamespace(revision=env["revision"])

    async def _rows(access: Any) -> tuple[None, list[tuple[str, Any]]]:
        env["scans"] += 1
        return None, ROWS

    monkeypatch.setattr(uf, "_access", lambda: _Access())
    monkeypatch.setattr(uf, "_rows", _rows)
    return env


@pytest.mark.asyncio
async def test_resolution_is_cached_per_filter_and_revision(
    stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    acme = _filter(_org("equals", "acme"))
    assert (await uf.resolve_user_filter(acme)).user_ids == ("u1", "u2")
    await uf.resolve_user_filter(_filter(_org("equals", "acme")))
    assert stored["scans"] == 1
    await uf.resolve_user_filter(_filter(_org("equals", "other")))
    assert stored["scans"] == 2
    stored["revision"] = 2
    await uf.resolve_user_filter(acme)
    assert stored["scans"] == 3
    now = [1e9]
    monkeypatch.setattr(uf.time, "monotonic", lambda: now[0])
    await uf.resolve_user_filter(acme)
    now[0] += uf.CACHE_TTL_SECONDS + 1
    await uf.resolve_user_filter(acme)
    assert stored["scans"] == 5


@pytest.mark.asyncio
async def test_summary_counts_without_returning_ids(stored: dict[str, Any]) -> None:
    summary = await uf.user_filter_summary(_filter(_org("equals", "acme")))
    assert (summary.known_users, summary.matched, summary.no_data) == (5, 2, 2)
    assert "u1" not in summary.model_dump_json()
    bare = await uf.user_filter_summary(None)
    assert bare.matched is None and [f.claim for f in bare.fields][0] == [
        "organisation"
    ]


def test_platform_access_not_installed_is_a_clear_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing() -> Any:
        raise HTTPException(404, "platform_access_disabled")

    monkeypatch.setattr(uf, "get_platform_access", _missing)
    with pytest.raises(HTTPException) as exc:
        uf._access()
    assert exc.value.status_code == 400


# --- authorization -------------------------------------------------------------

_OBSERVE = (OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID)


class _Rebac:
    def __init__(self, *allow: tuple[Any, str]) -> None:
        self.allow = set(allow)

    async def has_user_permission(self, user: Any, permission: Any, rid: str) -> bool:
        return (permission, rid) in self.allow

    async def check_user_permission_or_raise(
        self, user: Any, permission: Any, rid: str
    ) -> None:
        if (permission, rid) not in self.allow:
            raise AuthorizationError("u", str(permission), Resource.ORGANIZATION)


def _with_rebac(monkeypatch: pytest.MonkeyPatch, rebac: _Rebac) -> Any:
    container = SimpleNamespace(get_rebac_engine=lambda: rebac)
    monkeypatch.setattr(kpi_scope, "get_application_container", lambda r: container)
    monkeypatch.setattr(api, "get_application_container", lambda r: container)
    return object()


@pytest.mark.asyncio
async def test_team_admin_cannot_filter_their_team_by_attributes(
    monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> None:
    request = _with_rebac(monkeypatch, _Rebac((TeamPermission.CAN_READ_ANALYTICS, "a")))
    acme = _filter(_org("equals", "acme"))
    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, USER, [TeamId("a")], user_filter=acme)
    assert stored["scans"] == 0
    # Without the filter the same team admin reads their team.
    assert await resolve_kpi_scope(request, USER, [TeamId("a")]) == KpiScope(
        team_ids=(TeamId("a"),)
    )


@pytest.mark.asyncio
async def test_observer_scope_carries_the_matching_users(
    monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> None:
    request = _with_rebac(monkeypatch, _Rebac(_OBSERVE))
    acme = _filter(_org("equals", "acme"))
    scope = await resolve_kpi_scope(request, USER, [TeamId("a")], user_filter=acme)
    assert scope.team_ids == (TeamId("a"),)
    assert scope.user_ids == ("u1", "u2")
    assert KpiScope().user_ids is None


def _route(path: str) -> APIRoute:
    return next(
        r
        for r in api.build_kpi_router().routes
        if isinstance(r, APIRoute) and r.path == path
    )


@pytest.mark.asyncio
async def test_summary_route_is_for_observers_only(
    monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> None:
    route = _route("/kpi/user-filter")
    request = _with_rebac(monkeypatch, _Rebac())
    with pytest.raises(AuthorizationError):
        await route.endpoint(request=request, user=USER)
    request = _with_rebac(monkeypatch, _Rebac(_OBSERVE))
    raw = json.dumps({"conditions": [_org("equals", "acme")]})
    summary = await route.endpoint(request=request, user=USER, user_filter=raw)
    assert summary.matched == 2


def _preset_call(name: str, **extra: Any) -> dict[str, Any]:
    return dict(
        request=Request({"type": "http"}),
        since=SINCE,
        until=UNTIL,
        team_ids=[],
        bucket="auto",
        tz="Europe/Paris",
        user=USER,
        store=FakeKpiStore(),
        **extra,
    )


@pytest.mark.asyncio
async def test_router_refuses_a_filter_on_presets_it_cannot_narrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "resolve_kpi_scope", _fail_if_called)
    raw = json.dumps({"conditions": [_org("equals", "a")]})
    for name in ("storage_by_team", "agents_total", "agent_prompt_length_distribution"):
        with pytest.raises(HTTPException) as exc:
            await _route(f"/kpi/presets/{name}").endpoint(
                **_preset_call(name, user_filter=raw)
            )
        assert exc.value.status_code == 400


async def _fail_if_called(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("scope resolved for a refused request")


# --- every filterable preset filters every search --------------------------------

CLAUSE = {"terms": {"dims.user_id": ["u1", "u2"]}}


@pytest.fixture
def no_side_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_side_reads(monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preset", [p for p in PRESETS if p.user_filterable], ids=lambda p: p.name
)
async def test_every_filterable_preset_filters_every_search(
    preset: Any, no_side_reads: None
) -> None:
    store = FakeKpiStore()
    kwargs: dict[str, Any] = dict(
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        user_ids=("u1", "u2"),
    )
    if preset.team_scopable:
        kwargs["team_ids"] = ()
    if preset.bucketable or preset.zoned:
        kwargs["tz"] = "Europe/Paris"
    await preset.handler(store, **kwargs)
    assert store.bodies, f"{preset.name} ran no search"
    for body in store.bodies:
        assert CLAUSE in body["query"]["bool"]["filter"], preset.name


def test_analytics_presets_are_all_user_filterable() -> None:
    names = {p.name for p in PRESETS if p.user_filterable}
    analytics = {
        p.name
        for p in PRESETS
        if p.name.startswith("analytics_") and p.name != "analytics_teams_catalog"
    }
    assert analytics <= names
    assert not any(p.self_scoped for p in PRESETS if p.user_filterable)


def test_an_empty_match_filters_out_everyone() -> None:
    from control_plane_backend.kpi.presets.common import scope_filter

    assert scope_filter((), None) == []
    assert scope_filter((), ()) == [{"terms": {"dims.user_id": []}}]
