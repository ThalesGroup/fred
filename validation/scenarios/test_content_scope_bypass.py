# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Swift content-scope validation.

The old AUTHZ-05 gap was that corpus endpoints were organization-scoped: any
legacy Keycloak viewer/admin could call `/corpus/capabilities` without a team
context. The Swift contract is now explicit: callers must provide `team_id`, and
knowledge-flow-backend checks `TeamPermission.CAN_READ` on that concrete team.
"""

from __future__ import annotations

import pytest

from factory_config import TEAM_OPERATOR_USERNAME, TEST_TEAM, USERS


TEST_TEAM_MEMBERS = sorted(u for u, fu in USERS.items() if TEST_TEAM in fu.teams)
OTHER_TEAM_MEMBERS = sorted(u for u, fu in USERS.items() if fu.teams and TEST_TEAM not in fu.teams)
PLATFORM_ONLY_USERS = sorted(u for u, fu in USERS.items() if fu.platform_roles and not fu.teams)


def _resolve_team_id(cp, team_name: str = TEST_TEAM) -> str:
    if TEAM_OPERATOR_USERNAME is None:
        pytest.fail(
            f"No fixture user can see {team_name!r}; seed a team_admin/team_editor first.",
            pytrace=False,
        )
    teams = cp(TEAM_OPERATOR_USERNAME).get("/teams").json()
    by_name = {t.get("name"): t for t in teams}
    item = by_name.get(team_name)
    if item is None:
        pytest.fail(
            f"Team {team_name!r} is not visible to {TEAM_OPERATOR_USERNAME!r}; "
            f"teams returned: {sorted(n for n in by_name if n)}",
            pytrace=False,
        )
    return str(item.get("id") or item.get("name"))


def test_corpus_capabilities_requires_team_id(kf) -> None:
    """Corpus capabilities requires an explicit team_id instead of falling back to organization scope."""
    username = TEST_TEAM_MEMBERS[0]
    resp = kf(username).get("/corpus/capabilities")
    assert resp.status_code == 422, (
        f"/corpus/capabilities without team_id should be rejected as an invalid request, "
        f"got {resp.status_code}: {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", TEST_TEAM_MEMBERS)
def test_team_member_can_read_own_team_content_capabilities(username: str, cp, kf) -> None:
    """A member of the requested team can read that team's corpus capabilities."""
    team_id = _resolve_team_id(cp)
    resp = kf(username).get("/corpus/capabilities", params={"team_id": team_id})
    assert resp.status_code == 200, (
        f"{username} is a member of {TEST_TEAM} but could not read corpus capabilities: "
        f"{resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", PLATFORM_ONLY_USERS)
def test_platform_role_alone_cannot_read_team_content_capabilities(username: str, cp, kf) -> None:
    """A platform-only user cannot read a collaborative team's corpus capabilities."""
    team_id = _resolve_team_id(cp)
    resp = kf(username).get("/corpus/capabilities", params={"team_id": team_id})
    assert resp.status_code in (403, 404), (
        f"{username} has only platform role(s) {USERS[username].platform_roles}, yet read "
        f"{TEST_TEAM} corpus capabilities: {resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", OTHER_TEAM_MEMBERS)
def test_other_team_member_cannot_read_team_content_capabilities(username: str, cp, kf) -> None:
    """A member of another team cannot read the requested team's corpus capabilities."""
    team_id = _resolve_team_id(cp)
    resp = kf(username).get("/corpus/capabilities", params={"team_id": team_id})
    assert resp.status_code in (403, 404), (
        f"{username} belongs to {USERS[username].teams}, not {TEST_TEAM}, yet read corpus "
        f"capabilities: {resp.status_code} {resp.text[:200]}"
    )
