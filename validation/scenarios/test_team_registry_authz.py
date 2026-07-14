# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Swift team-registry governance validation (AUTHZ-05 review item 9).

Teams are no longer Keycloak groups - a team is a `team_metadata` row plus its
OpenFGA relations, and its existence is governed by three platform-admin-only,
registry-scoped capabilities that grant nothing about a team's own content:
`can_create_team` (`POST /teams`, one-shot bootstrap with an explicit initial
admin), `can_list_all_teams` (`GET /teams/all`, bypasses the caller's own
CAN_READ visibility filter), `can_delete_team` (`DELETE /teams/{id}`), and
`can_rescue_team_admin` (`POST /teams/{id}/rescue-admin`, only succeeds when
the team currently has zero team_admin).

What this file does NOT attempt: driving a team to a genuine zero-admin state
through the public API. `remove_team_member` (full member removal) and
`revoke_team_member_role` (AUTHZ-06 granular single-role revoke, the only
mutation left on `/teams/{team_id}/members/{user_id}` - there is no bulk
PATCH) both enforce `_ensure_team_keeps_at_least_one_admin` symmetrically
(self-revoke included), so there is no documented, self-service path to an
orphaned team - rescue-admin is a break-glass tool for an out-of-band state
(e.g. data migration), not a flow this black-box suite can legitimately
construct. What IS tested instead: that guard itself (a team_admin cannot
revoke their own team_admin role out of existence), and that rescue-admin is
refused - loudly, with no side effect - against any team that still has an
admin.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

from factory_config import USERS


def _platform_admin_username() -> str:
    for username, user in sorted(USERS.items()):
        if user.is_platform_admin:
            return username
    pytest.fail("No platform_admin user found in validation configuration.", pytrace=False)


def _jwt_sub(token: str) -> str:
    """Extract the Keycloak subject from a JWT already obtained from Keycloak."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    sub = decoded.get("sub")
    assert sub, "Keycloak token has no sub claim"
    return str(sub)


NON_PLATFORM_ADMINS = sorted(u for u in USERS if not USERS[u].is_platform_admin)


@pytest.fixture
def disposable_team(cp, token_for):
    """A throwaway team, bootstrapped by the platform admin with oscar as its
    sole initial team_admin, deleted again at the end of the test.

    Isolated from the seeded northbridge/fredlab/swiftpost teams on purpose -
    the rescue-admin guard checks below are inherently about manipulating a
    team's admin set, which must never touch shared fixture teams other
    scenario files depend on.
    """
    admin_username = _platform_admin_username()
    assert "oscar" in USERS, "This scenario needs the identity-only fixture user 'oscar'"
    oscar_sub = _jwt_sub(token_for("oscar"))

    admin = cp(admin_username)
    name = f"val-registry-{uuid.uuid4().hex[:8]}"
    created = admin.post("/teams", json={"name": name, "initial_team_admin_ids": [oscar_sub]})
    assert created.status_code == 201, (
        f"{admin_username} (platform_admin) could not bootstrap a disposable team: "
        f"{created.status_code} {created.text[:200]}"
    )
    team = created.json()
    yield team

    # pytest runs this teardown even if the test body above failed (yield
    # fixtures behave like try/finally around the test). A teardown error is
    # reported separately from the test's own pass/fail, so asserting here is
    # how a failed cleanup actually surfaces instead of leaking a disposable
    # team into the registry silently.
    deleted = admin.delete(f"/teams/{team['id']}")
    assert deleted.status_code == 204, (
        f"cleanup failed: could not delete disposable team {team['id']!r}: "
        f"{deleted.status_code} {deleted.text[:200]}"
    )


@pytest.mark.parametrize("username", NON_PLATFORM_ADMINS)
def test_non_platform_admin_cannot_create_team(username: str, cp) -> None:
    """A non-platform-admin cannot bootstrap a new team. [username={username}]"""
    resp = cp(username).post(
        "/teams",
        json={"name": f"deny-{uuid.uuid4().hex[:8]}", "initial_team_admin_ids": [username]},
    )
    assert resp.status_code == 403, (
        f"{username} is not platform_admin, yet created a team: {resp.status_code} {resp.text[:200]}"
    )


def test_platform_admin_sees_disposable_team_in_registry_without_membership(
    disposable_team, cp
) -> None:
    """The platform admin sees a freshly bootstrapped team in /teams/all despite holding no relation on it."""
    admin_username = _platform_admin_username()
    resp = cp(admin_username).get("/teams/all")
    assert resp.status_code == 200
    ids = {t.get("id") for t in resp.json()}
    assert disposable_team["id"] in ids, (
        f"{admin_username} (platform_admin) does not see the disposable team in /teams/all "
        f"despite holding no team relation on it - registry visibility must not be filtered "
        f"by the caller's own CAN_READ."
    )


@pytest.mark.parametrize("username", NON_PLATFORM_ADMINS)
def test_non_platform_admin_cannot_list_all_teams(username: str, cp) -> None:
    """A non-platform-admin cannot call the registry-wide /teams/all. [username={username}]"""
    resp = cp(username).get("/teams/all")
    assert resp.status_code == 403, (
        f"{username} is not platform_admin, yet listed the full team registry: "
        f"{resp.status_code} {resp.text[:200]}"
    )


def test_sole_team_admin_cannot_revoke_their_own_team_admin_role(disposable_team, cp, token_for) -> None:
    """oscar, the disposable team's only team_admin, cannot revoke his own team_admin role."""
    oscar_sub = _jwt_sub(token_for("oscar"))
    resp = cp("oscar").delete(f"/teams/{disposable_team['id']}/members/{oscar_sub}/roles/team_admin")
    assert resp.status_code == 409, (
        f"oscar is the sole team_admin of the disposable team; self-revoke of team_admin should be "
        f"refused (a team must always keep at least one team_admin, AUTHZ-06 §35), got "
        f"{resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", [u for u in NON_PLATFORM_ADMINS if u != "oscar"])
def test_non_platform_admin_cannot_rescue_team_admin(
    username: str, disposable_team, cp, token_for
) -> None:
    """A non-platform-admin cannot call rescue-admin, even oscar as the team's own admin. [username={username}]"""
    resp = cp(username).post(
        f"/teams/{disposable_team['id']}/rescue-admin",
        json={"user_id": _jwt_sub(token_for(username))},
    )
    assert resp.status_code == 403, (
        f"{username} is not platform_admin, yet called rescue-admin "
        f"(username's own team_admin status on the team, if any, must not substitute for the "
        f"platform-admin gate): {resp.status_code} {resp.text[:200]}"
    )


def test_platform_admin_cannot_rescue_a_team_that_still_has_an_admin(
    disposable_team, cp, token_for
) -> None:
    """The platform admin's rescue-admin call is refused while the disposable team still has oscar as admin."""
    admin_username = _platform_admin_username()
    nina_sub = _jwt_sub(token_for("nina"))
    resp = cp(admin_username).post(
        f"/teams/{disposable_team['id']}/rescue-admin",
        json={"user_id": nina_sub},
    )
    assert resp.status_code == 409, (
        f"The disposable team still has oscar as team_admin; rescue-admin must refuse "
        f"(the zero-admin guard exists specifically to prevent the reverted §24.7 escalation), "
        f"got {resp.status_code} {resp.text[:200]}"
    )

    # Re-read through /teams/all (bypasses CAN_READ, same as the visibility test above) -
    # the platform admin holds no relation on the disposable team and cannot use
    # /teams/{id}/members here, which is exactly the point: registry governance must
    # never require a content-level relation.
    registry = cp(admin_username).get("/teams/all")
    assert registry.status_code == 200
    disposable_now = next(t for t in registry.json() if t.get("id") == disposable_team["id"])
    admin_ids = {a["id"] for a in disposable_now.get("admins", [])}
    assert admin_ids == {_jwt_sub(token_for("oscar"))}, (
        f"rescue-admin must write no relation when refused; team_admin set is now {admin_ids!r}"
    )


@pytest.mark.parametrize("username", NON_PLATFORM_ADMINS)
def test_non_platform_admin_cannot_delete_team(username: str, disposable_team, cp) -> None:
    """A non-platform-admin cannot delete a team's registry entry. [username={username}]"""
    resp = cp(username).delete(f"/teams/{disposable_team['id']}")
    assert resp.status_code == 403, (
        f"{username} is not platform_admin, yet deleted a team: {resp.status_code} {resp.text[:200]}"
    )


def test_platform_admin_can_delete_disposable_team(cp, token_for) -> None:
    """The platform admin can bootstrap and then delete a disposable team, which then disappears from the registry."""
    admin_username = _platform_admin_username()
    oscar_sub = _jwt_sub(token_for("oscar"))
    admin = cp(admin_username)

    name = f"val-registry-delete-{uuid.uuid4().hex[:8]}"
    created = admin.post("/teams", json={"name": name, "initial_team_admin_ids": [oscar_sub]})
    assert created.status_code == 201, created.text[:200]
    team_id = created.json()["id"]

    deleted = admin.delete(f"/teams/{team_id}")
    assert deleted.status_code == 204, (
        f"{admin_username} (platform_admin) could not delete the disposable team: "
        f"{deleted.status_code} {deleted.text[:200]}"
    )

    after = admin.get("/teams/all")
    assert after.status_code == 200
    ids = {t.get("id") for t in after.json()}
    assert team_id not in ids, "deleted team is still visible in /teams/all"
