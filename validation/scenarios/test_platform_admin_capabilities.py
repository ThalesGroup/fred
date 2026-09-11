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
every non-admin role is defined as `[user] or platform_admin` (`schema.fga`),
so a platform_admin appears in `platform_roles` under every role - it is not
an exclusive choice between them. Do not "simplify" this back to a direct
comparison with the seeded role without re-reading the schema.
"""

from __future__ import annotations

import pytest

from factory_config import USERS


def _platform_admin_username() -> str:
    for username, user in sorted(USERS.items()):
        if user.is_platform_admin:
            return username
    raise AssertionError("No platform_admin user found in validation configuration.")


NON_PLATFORM_ADMINS = sorted(u for u in USERS if not USERS[u].is_platform_admin)


def _bootstrap_roles(cp, username: str) -> list[str]:
    resp = cp(username).get("/frontend/bootstrap")
    assert resp.status_code == 200, f"{username}: {resp.status_code} {resp.text[:200]}"
    return resp.json()["permissions"]["platform_roles"]


@pytest.mark.parametrize("username", sorted(USERS))
def test_bootstrap_reports_platform_admin_role_from_openfga(username: str, cp) -> None:
    """FrontendBootstrap.permissions.platform_roles carries platform_admin iff seeded. [username={username}]"""
    roles = _bootstrap_roles(cp, username)
    expected = USERS[username].is_platform_admin
    assert ("platform_admin" in roles) is expected, (
        f"{username}: expected platform_admin={expected}, got roles={roles!r} - admin UI "
        f"gating must be driven by the OpenFGA platform_admin relation, never a Keycloak "
        f"role (AUTHZ-05 review item 4)."
    )


@pytest.mark.parametrize("username", sorted(USERS))
def test_bootstrap_reports_every_delegated_role_through_the_admin_union(username: str, cp) -> None:
    """A platform_admin holds every delegated role through the schema union. [username={username}]"""
    roles = _bootstrap_roles(cp, username)
    user = USERS[username]
    delegated = ("platform_observer", "team_manager", "feature_manager", "prompt_editor")

    if user.is_platform_admin:
        assert set(delegated) <= set(roles), (
            f"{username} is platform_admin, so schema.fga's `[user] or platform_admin` "
            f"unions must put every delegated role in platform_roles; got {roles!r}."
        )
        return

    assert ("platform_observer" in roles) is user.is_platform_observer, (
        f"{username}: expected platform_observer={user.is_platform_observer}, got {roles!r}."
    )
    # The validation fixtures seed no delegated-role holder yet, so a non-admin
    # must carry none of them.
    assert not (set(delegated[1:]) & set(roles)), (
        f"{username} holds a delegated role no fixture grants: {roles!r}."
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
