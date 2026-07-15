# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
AUTHZ-06 cumulative team roles - explicit, dedicated proof (RFC Part 7 §33-39).

Swift team roles are cumulative and independent: a member may hold
team_admin, team_editor and team_analyst on the same team at once, each
granted/revoked one at a time (POST/DELETE .../roles), and the effective
capability set is the union of every role currently held - never a single
"primary" role.

The `config/configuration.yaml` fredlab fixtures exist specifically to prove
this against the real running stack:
- marc   - team_admin only
- bob    - team_editor only (also editor of northbridge, irrelevant here)
- elena  - team_analyst only
- priya  - team_admin + team_editor + team_analyst at once

This file proves three things marc/bob/elena/priya alone do not, and that no
other scenario file asserts explicitly:
1. `/teams/{fredlab_id}/members` reports the exact relation set held by each
   persona - a list, not a single relation (AUTHZ-06 `TeamMember.relations`).
2. `/teams/{fredlab_id}` (`TeamWithPermissions.permissions`) reports the
   capability set schema.fga actually derives from those relations, proving
   the isolated personas do NOT get each other's capabilities and priya gets
   their union - including the one asymmetry in the schema worth locking in:
   `can_read_conversations_for_evaluation` is `team_analyst`-only and is NOT
   granted by `team_admin` alone (schema.fga), so marc must not have it while
   elena and priya do.
3. priya can actually exercise an admin-gated operation (add then remove a
   member) and an editor-gated operation (create then delete a prompt) using
   her cumulative grant - not just have the capability listed.

No analyst-gated write route exists in this suite that is both stable and
free of external/costly dependencies (running an evaluation is explicitly out
of scope for this black-box suite). Analyst capability is therefore verified
here only via the permissions the backend reports (point 2); actually
exercising `can_run_evaluations`/`can_manage_evaluation_corpus` end-to-end is
tracked as a separate, live-only follow-up, not asserted here.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

from factory_config import TEST_TEAM, USERS


ADMIN_ONLY_CAPS = {
    "can_update_info",
    "can_administer_members",
    "can_administer_editors",
    "can_administer_analysts",
    "can_administer_admins",
}
EDITOR_ONLY_CAPS = {"can_update_resources", "can_update_agents"}
ANALYST_ONLY_CAPS = {
    "can_run_evaluations",
    "can_manage_evaluation_corpus",
    "can_read_conversations_for_evaluation",
}
# Granted by team_admin too (schema.fga: "team_analyst or team_admin") -
# the one deliberate exception is can_read_conversations_for_evaluation
# (team_analyst only, see module docstring).
ADMIN_AND_ANALYST_CAPS = {"can_run_evaluations", "can_manage_evaluation_corpus"}
MEMBER_BASELINE_CAPS = {"can_read", "can_read_members", "can_read_conversations", "can_use_team_agents"}


def _platform_admin_username() -> str:
    for username, user in sorted(USERS.items()):
        if user.is_platform_admin:
            return username
    raise AssertionError("No platform_admin user found in validation configuration.")


def _jwt_sub(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    sub = decoded.get("sub")
    assert sub, "Keycloak token has no sub claim"
    return str(sub)


MARC, BOB, ELENA, PRIYA = "marc", "bob", "elena", "priya"


@pytest.fixture(scope="module")
def fredlab_id(cp) -> str:
    admin = cp(_platform_admin_username())
    teams = admin.get("/teams/all").json()
    item = next((t for t in teams if t.get("name") == TEST_TEAM), None)
    if item is None:
        pytest.fail(
            f"Team {TEST_TEAM!r} is not visible in /teams/all.\n-> Is configuration.yaml seeded (make docker-up)?",
            pytrace=False,
        )
    return str(item.get("id") or item.get("name"))


@pytest.fixture(scope="module")
def member_relations(fredlab_id, cp, token_for) -> dict[str, set[str]]:
    resp = cp(MARC).get(f"/teams/{fredlab_id}/members")
    assert resp.status_code == 200, f"{MARC}: {resp.status_code} {resp.text[:200]}"
    by_sub: dict[str, set[str]] = {}
    for member in resp.json():
        user_id = str((member.get("user") or {}).get("id") or "")
        if user_id:
            by_sub[user_id] = set(member.get("relations") or [])
    return {
        username: by_sub.get(_jwt_sub(token_for(username)), set())
        for username in (MARC, BOB, ELENA, PRIYA)
    }


def test_member_list_reports_exactly_marcs_single_admin_relation(member_relations) -> None:
    """{team}'s member list reports marc holding exactly [team_admin], nothing else."""
    assert member_relations[MARC] == {"team_admin"}, member_relations[MARC]


def test_member_list_reports_exactly_bobs_single_editor_relation(member_relations) -> None:
    """{team}'s member list reports bob holding exactly [team_editor], nothing else."""
    assert member_relations[BOB] == {"team_editor"}, member_relations[BOB]


def test_member_list_reports_exactly_elenas_single_analyst_relation(member_relations) -> None:
    """{team}'s member list reports elena holding exactly [team_analyst], nothing else."""
    assert member_relations[ELENA] == {"team_analyst"}, member_relations[ELENA]


def test_member_list_reports_priyas_three_cumulative_relations(member_relations) -> None:
    """{team}'s member list reports priya holding all three of team_admin/team_editor/team_analyst at once."""
    assert member_relations[PRIYA] == {"team_admin", "team_editor", "team_analyst"}, member_relations[PRIYA]


@pytest.fixture(scope="module")
def team_permissions(fredlab_id, cp) -> dict[str, set[str]]:
    perms: dict[str, set[str]] = {}
    for username in (MARC, BOB, ELENA, PRIYA):
        resp = cp(username).get(f"/teams/{fredlab_id}")
        assert resp.status_code == 200, f"{username}: {resp.status_code} {resp.text[:200]}"
        perms[username] = set(resp.json().get("permissions") or [])
    return perms


def test_marc_has_admin_capabilities_but_not_editor_or_analyst_only_ones(team_permissions) -> None:
    """marc (team_admin only) has admin capabilities on {team}, but no editor-only or analyst-only capability."""
    marc_perms = team_permissions[MARC]
    assert ADMIN_ONLY_CAPS <= marc_perms, f"marc missing admin capabilities: {ADMIN_ONLY_CAPS - marc_perms}"
    assert not (EDITOR_ONLY_CAPS & marc_perms), f"marc has editor-only capabilities it should not: {EDITOR_ONLY_CAPS & marc_perms}"
    assert ADMIN_AND_ANALYST_CAPS <= marc_perms, (
        f"marc missing capabilities schema.fga grants to team_admin too: {ADMIN_AND_ANALYST_CAPS - marc_perms}"
    )
    analyst_only_gap = ANALYST_ONLY_CAPS - ADMIN_AND_ANALYST_CAPS
    assert not (analyst_only_gap & marc_perms), (
        f"marc unexpectedly has {analyst_only_gap & marc_perms} - "
        f"can_read_conversations_for_evaluation is team_analyst-only in schema.fga, team_admin does not grant it"
    )


def test_bob_has_editor_capabilities_but_not_admin_or_analyst_ones(team_permissions) -> None:
    """bob (team_editor only) has editor capabilities on {team}, but no admin or analyst capability."""
    bob_perms = team_permissions[BOB]
    assert EDITOR_ONLY_CAPS <= bob_perms, f"bob missing editor capabilities: {EDITOR_ONLY_CAPS - bob_perms}"
    assert not (ADMIN_ONLY_CAPS & bob_perms), f"bob has admin capabilities it should not: {ADMIN_ONLY_CAPS & bob_perms}"
    assert not (ANALYST_ONLY_CAPS & bob_perms), f"bob has analyst capabilities it should not: {ANALYST_ONLY_CAPS & bob_perms}"


def test_elena_has_analyst_capabilities_but_not_admin_or_editor_ones(team_permissions) -> None:
    """elena (team_analyst only) has analyst capabilities on {team}, but no admin or editor capability."""
    elena_perms = team_permissions[ELENA]
    assert ANALYST_ONLY_CAPS <= elena_perms, f"elena missing analyst capabilities: {ANALYST_ONLY_CAPS - elena_perms}"
    assert not (ADMIN_ONLY_CAPS & elena_perms), f"elena has admin capabilities it should not: {ADMIN_ONLY_CAPS & elena_perms}"
    assert not (EDITOR_ONLY_CAPS & elena_perms), f"elena has editor capabilities it should not: {EDITOR_ONLY_CAPS & elena_perms}"


def test_priya_has_the_union_of_all_three_roles_capabilities(team_permissions) -> None:
    """priya (team_admin + team_editor + team_analyst) has the full union of all three roles' capabilities on {team}."""
    priya_perms = team_permissions[PRIYA]
    expected = ADMIN_ONLY_CAPS | EDITOR_ONLY_CAPS | ANALYST_ONLY_CAPS | MEMBER_BASELINE_CAPS
    missing = expected - priya_perms
    assert not missing, f"priya is missing capabilities from the expected union: {missing}"


def test_priya_can_exercise_an_admin_gated_operation(fredlab_id, cp, token_for) -> None:
    """priya, holding team_admin among her cumulative roles, can add and then remove a {team} member."""
    assert "oscar" in USERS, "This scenario needs the identity-only fixture user 'oscar'"
    oscar_sub = _jwt_sub(token_for("oscar"))
    priya = cp(PRIYA)

    # Refuse to mutate a persona that isn't in the expected starting state -
    # oscar is relied on elsewhere as an identity-only control (zero OpenFGA
    # grant); if he already has a relation here, something upstream is wrong
    # and this test must not paper over it by adding/removing on top of it.
    members_before = priya.get(f"/teams/{fredlab_id}/members")
    assert members_before.status_code == 200, (
        f"could not read {TEST_TEAM} members before mutating: "
        f"{members_before.status_code} {members_before.text[:200]}"
    )
    oscar_already_member = any(
        str((m.get("user") or {}).get("id") or "") == oscar_sub for m in members_before.json()
    )
    assert not oscar_already_member, (
        f"oscar already holds a relation on {TEST_TEAM} before this test ran - refusing to "
        f"add/remove on top of unexpected pre-existing state"
    )

    added = False
    try:
        add_resp = priya.post(f"/teams/{fredlab_id}/members", json={"user_id": oscar_sub, "relation": "team_member"})
        assert add_resp.status_code in (200, 201, 202, 204), (
            f"priya (team_admin among her cumulative roles) could not add a member to {TEST_TEAM}: "
            f"{add_resp.status_code} {add_resp.text[:200]}"
        )
        added = True
    finally:
        if added:
            remove_resp = priya.delete(f"/teams/{fredlab_id}/members/{oscar_sub}")
            assert remove_resp.status_code in (200, 202, 204), (
                f"priya could not remove the member she just added from {TEST_TEAM} - cleanup "
                f"failed, oscar may still be a member: {remove_resp.status_code} "
                f"{remove_resp.text[:200]}"
            )


def test_priya_can_exercise_an_editor_gated_operation(fredlab_id, cp) -> None:
    """priya, holding team_editor among her cumulative roles, can create and then delete a {team} prompt."""
    priya = cp(PRIYA)
    name = f"val-cumulative-{uuid.uuid4().hex[:8]}"
    prompt_id: str | None = None
    try:
        create_resp = priya.post(f"/teams/{fredlab_id}/prompts", json={"name": name, "text": "Say exactly: validation-ok"})
        assert create_resp.status_code == 201, (
            f"priya (team_editor among her cumulative roles) could not create a prompt in {TEST_TEAM}: "
            f"{create_resp.status_code} {create_resp.text[:200]}"
        )
        prompt_id = create_resp.json()["id"]
    finally:
        if prompt_id is not None:
            delete_resp = priya.delete(f"/teams/{fredlab_id}/prompts/{prompt_id}")
            assert delete_resp.status_code in (200, 202, 204), (
                f"priya could not delete the prompt she just created in {TEST_TEAM} - cleanup "
                f"failed, prompt {prompt_id} may still exist: {delete_resp.status_code} "
                f"{delete_resp.text[:200]}"
            )
