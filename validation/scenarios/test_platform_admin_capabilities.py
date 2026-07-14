# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Swift platform_admin / platform_observer positive-capability validation.

The other scenario files prove the *denial* side of platform roles well
(alice/gabriel see no team data). This file proves the other half: that the
capabilities a platform role is supposed to grant actually work, and that
`FrontendBootstrap.permissions` - the single source of truth the frontend
gates admin/observer UI on (AUTHZ-05 review item 4; never Keycloak roles) -
reports them correctly for every seeded user.

One schema subtlety this file locks in explicitly (verified live against the
running stack before writing these assertions, not assumed from the docs):
`organization#platform_observer` is defined as `[user] or platform_admin`
(`schema.fga`), so a platform_admin computes as `is_platform_observer: true`
too - it is not an exclusive-or between the two roles. Do not "simplify" this
back to `is_platform_observer == user.is_platform_observer` without re-reading
the schema.
"""

from __future__ import annotations

import pytest

from factory_config import USERS


def _platform_admin_username() -> str:
    for username, user in sorted(USERS.items()):
        if user.is_platform_admin:
            return username
    pytest.fail("No platform_admin user found in validation configuration.", pytrace=False)


NON_PLATFORM_ADMINS = sorted(u for u in USERS if not USERS[u].is_platform_admin)


@pytest.mark.parametrize("username", sorted(USERS))
def test_bootstrap_reports_platform_admin_flag_from_openfga(username: str, cp) -> None:
    """FrontendBootstrap.permissions.is_platform_admin matches the seeded platform role. [username={username}]"""
    resp = cp(username).get("/frontend/bootstrap")
    assert resp.status_code == 200, f"{username}: {resp.status_code} {resp.text[:200]}"
    permissions = resp.json()["permissions"]
    expected = USERS[username].is_platform_admin
    assert permissions["is_platform_admin"] is expected, (
        f"{username}: expected is_platform_admin={expected}, got "
        f"{permissions['is_platform_admin']!r} - admin UI gating must be driven by the OpenFGA "
        f"platform_admin relation, never a Keycloak role (AUTHZ-05 review item 4)."
    )


@pytest.mark.parametrize("username", sorted(USERS))
def test_bootstrap_reports_platform_observer_flag_including_admin_union(username: str, cp) -> None:
    """FrontendBootstrap.permissions.is_platform_observer matches platform_observer OR platform_admin. [username={username}]"""
    resp = cp(username).get("/frontend/bootstrap")
    assert resp.status_code == 200, f"{username}: {resp.status_code} {resp.text[:200]}"
    permissions = resp.json()["permissions"]
    user = USERS[username]
    expected = user.is_platform_observer or user.is_platform_admin
    assert permissions["is_platform_observer"] is expected, (
        f"{username}: expected is_platform_observer={expected} "
        f"(platform_observer={user.is_platform_observer}, platform_admin={user.is_platform_admin}; "
        f"schema.fga defines organization#platform_observer as '[user] or platform_admin'), got "
        f"{permissions['is_platform_observer']!r}."
    )


def test_platform_admin_can_list_users(cp) -> None:
    """The platform admin can list the user-administration surface."""
    admin_username = _platform_admin_username()
    resp = cp(admin_username).get("/users")
    assert resp.status_code == 200, (
        f"{admin_username} (platform_admin) could not list users: {resp.status_code} {resp.text[:200]}"
    )
    usernames = {u.get("username") for u in resp.json()}
    assert usernames & set(USERS), (
        f"user-administration list does not contain any seeded fixture user: {sorted(usernames)}"
    )


@pytest.mark.parametrize("username", NON_PLATFORM_ADMINS)
def test_non_platform_admin_cannot_list_users(username: str, cp) -> None:
    """A non-platform-admin cannot read the user-administration list. [username={username}]"""
    resp = cp(username).get("/users")
    assert resp.status_code == 403, (
        f"{username} is not platform_admin, yet read the user-administration list: "
        f"{resp.status_code} {resp.text[:200]}"
    )
