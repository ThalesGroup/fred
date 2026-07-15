# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Swift platform-role isolation validation.

Keycloak is identity-only for users in the clean Swift seed. Platform roles are
stored OpenFGA relations on organization:fred and must never grant collaborative
team data. The concrete platform users are read from config/configuration.yaml so
this file stays aligned with the factory seed (today: alice=platform_admin,
gabriel=platform_observer).
"""

from __future__ import annotations

import pytest

from factory_config import TEAM_OPERATOR_USERNAME, TEST_TEAM, USERS


PLATFORM_ONLY_USERS = sorted(
    username
    for username, user in USERS.items()
    if user.platform_roles and not user.teams and not user.app_roles
)
IDENTITY_ONLY_USERS = sorted(
    username
    for username, user in USERS.items()
    if not user.platform_roles and not user.teams and not user.app_roles
)


def _resolve_team_id(cp, team_name: str) -> str:
    """Resolve a team name to its id via the configured team operator."""
    if TEAM_OPERATOR_USERNAME is None:
        pytest.fail(
            f"No fixture user can administer/enroll in {team_name!r}; seed a team_admin/team_editor first.",
            pytrace=False,
        )
    teams = cp(TEAM_OPERATOR_USERNAME).get("/teams").json()
    by_name = {t.get("name"): t for t in teams}
    item = by_name.get(team_name)
    if item is None:
        pytest.fail(
            f"Team {team_name!r} is not visible to {TEAM_OPERATOR_USERNAME!r} in /teams.\n"
            f"Teams returned: {sorted(n for n in by_name if n)}\n"
            f"-> Is configuration.yaml seeded (make docker-up / make openfga-post-install)?",
            pytrace=False,
        )
    return str(item.get("id") or item.get("name"))


@pytest.fixture(scope="module")
def fredlab_id(cp) -> str:
    return _resolve_team_id(cp, TEST_TEAM)


@pytest.mark.parametrize("username", PLATFORM_ONLY_USERS)
def test_platform_role_alone_grants_no_team_data(username: str, fredlab_id, cp) -> None:
    """{username} holds only a platform role and cannot read {team}'s catalog."""
    resp = cp(username).get(f"/teams/{fredlab_id}/agent-templates")
    assert resp.status_code in (403, 404), (
        f"{username} holds only a platform relation and no team relation, yet got "
        f"{resp.status_code} from /teams/{fredlab_id}/agent-templates - a platform "
        f"role must never grant team data visibility."
    )


@pytest.mark.parametrize("username", PLATFORM_ONLY_USERS)
def test_platform_role_alone_sees_no_collaborative_team(username: str, cp) -> None:
    """{username} holds only a platform role and sees zero collaborative teams."""
    items = cp(username).get("/teams").json()
    collaborative = [t for t in items if not str(t.get("id", "")).startswith("personal-")]
    assert not collaborative, (
        f"{username} unexpectedly sees collaborative teams: "
        f"{[t.get('name') for t in collaborative]!r}"
    )


@pytest.mark.parametrize("username", IDENTITY_ONLY_USERS)
def test_identity_only_user_sees_no_collaborative_team(username: str, cp) -> None:
    """{username} has no role at all and sees zero collaborative teams."""
    items = cp(username).get("/teams").json()
    collaborative = [t for t in items if not str(t.get("id", "")).startswith("personal-")]
    assert not collaborative, (
        f"{username} unexpectedly sees collaborative teams: "
        f"{[t.get('name') for t in collaborative]!r}"
    )


def test_swift_platform_fixture_users_are_registered() -> None:
    """Sanity check: the clean Swift platform users exist in the parsed factory matrix."""
    expected = {"alice", "gabriel"}
    missing = expected - set(USERS)
    assert not missing, f"Expected Swift platform fixture users missing: {sorted(missing)}"
    assert PLATFORM_ONLY_USERS, "Expected at least one platform-only fixture user"
