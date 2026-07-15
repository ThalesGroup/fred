# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Swift prompt-library authorization validation.

AUTHZ-05 review item 1a found five prompt-mutation endpoints (create, replace,
delete, promote, score) silently falling back to CAN_READ (team_member or
public) instead of CAN_UPDATE_RESOURCES (team_editor) - any visitor of a public
team could mutate its prompt library. A later pass (review item 10, found while
preparing this live campaign) found that `promote` never checked the *target*
team at all: a team_editor of team A could copy a prompt's text into any
team_id, including one they held no relation to. Both fixes are locked here
against the real running stack, on top of the unit-level wiring tests in
`apps/control-plane-backend/tests/test_product_api_authz.py`.
"""

from __future__ import annotations

import uuid

import pytest

from factory_config import TEST_TEAM, USERS


FREDLAB_MEMBERS = sorted(u for u, fu in USERS.items() if TEST_TEAM in fu.teams)
FREDLAB_EDITORS = sorted(u for u in FREDLAB_MEMBERS if USERS[u].is_team_editor_in(TEST_TEAM))
FREDLAB_NON_EDITORS = sorted(u for u in FREDLAB_MEMBERS if u not in FREDLAB_EDITORS)
OTHER_TEAM_MEMBERS = sorted(u for u, fu in USERS.items() if fu.teams and TEST_TEAM not in fu.teams)


def _platform_admin_username() -> str:
    for username, user in sorted(USERS.items()):
        if user.is_platform_admin:
            return username
    raise AssertionError("No platform_admin user found in validation configuration.")


def _resolve_team_id(cp, team_name: str) -> str:
    """Resolve a team name to its id via the platform admin's `/teams/all`.

    Unlike the single-team helpers in the other scenario files, prompt promote
    needs ids for teams the acting user does *not* belong to, so this resolves
    through the registry-governance endpoint instead of the caller's own
    `/teams`.
    """
    admin = cp(_platform_admin_username())
    teams = admin.get("/teams/all").json()
    by_name = {t.get("name"): t for t in teams}
    item = by_name.get(team_name)
    if item is None:
        pytest.fail(
            f"Team {team_name!r} is not visible in /teams/all.\n"
            f"Teams returned: {sorted(n for n in by_name if n)}\n"
            f"-> Is configuration.yaml seeded (make docker-up)?",
            pytrace=False,
        )
    return str(item.get("id") or item.get("name"))


@pytest.fixture(scope="module")
def fredlab_id(cp) -> str:
    return _resolve_team_id(cp, TEST_TEAM)


@pytest.fixture(scope="module")
def northbridge_id(cp) -> str:
    return _resolve_team_id(cp, "northbridge")


@pytest.fixture(scope="module")
def swiftpost_id(cp) -> str:
    return _resolve_team_id(cp, "swiftpost")


@pytest.fixture
def created_prompt(fredlab_id, cp):
    """A fresh fredlab prompt created by a fredlab team_editor, cleaned up after."""
    assert FREDLAB_EDITORS, "Need at least one fredlab team_editor fixture user"
    editor = cp(FREDLAB_EDITORS[0])
    name = f"val-prompt-{uuid.uuid4().hex[:8]}"
    resp = editor.post(
        f"/teams/{fredlab_id}/prompts",
        json={"name": name, "text": "Say exactly: validation-ok"},
    )
    assert resp.status_code == 201, (
        f"{FREDLAB_EDITORS[0]} (team_editor of {TEST_TEAM}) could not create a prompt: "
        f"{resp.status_code} {resp.text[:200]}"
    )
    prompt = resp.json()
    yield prompt

    editor.delete(f"/teams/{fredlab_id}/prompts/{prompt['id']}")


def test_team_editor_can_create_prompt(created_prompt) -> None:
    """{editor} (team_editor of {team}) can create a team prompt."""
    assert created_prompt.get("id")
    assert created_prompt.get("name", "").startswith("val-prompt-")


@pytest.mark.parametrize("username", FREDLAB_NON_EDITORS)
def test_non_editor_member_cannot_create_prompt(username: str, fredlab_id, cp) -> None:
    """A {team} member without team_editor cannot create a team prompt. [username={username}]"""
    resp = cp(username).post(
        f"/teams/{fredlab_id}/prompts",
        json={"name": f"deny-{uuid.uuid4().hex[:8]}", "text": "should not be created"},
    )
    assert resp.status_code == 403, (
        f"{username} is a member of {TEST_TEAM} but not team_editor, yet created a prompt: "
        f"{resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", OTHER_TEAM_MEMBERS)
def test_other_team_member_cannot_create_prompt(username: str, fredlab_id, cp) -> None:
    """A member of another team cannot create a prompt in {team}. [username={username}]"""
    resp = cp(username).post(
        f"/teams/{fredlab_id}/prompts",
        json={"name": f"deny-{uuid.uuid4().hex[:8]}", "text": "should not be created"},
    )
    assert resp.status_code in (403, 404), (
        f"{username} belongs to {USERS[username].teams}, not {TEST_TEAM}, yet created a prompt: "
        f"{resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", FREDLAB_MEMBERS)
def test_team_member_can_read_team_prompts(username: str, fredlab_id, cp, created_prompt) -> None:
    """Any member of {team} can read its prompt library. [username={username}]"""
    resp = cp(username).get(f"/teams/{fredlab_id}/prompts")
    assert resp.status_code == 200, (
        f"{username} is a member of {TEST_TEAM} but could not read its prompts: "
        f"{resp.status_code} {resp.text[:200]}"
    )
    ids = {p.get("id") for p in resp.json()}
    assert created_prompt["id"] in ids


@pytest.mark.parametrize("username", OTHER_TEAM_MEMBERS)
def test_other_team_member_cannot_read_team_prompts(username: str, fredlab_id, cp) -> None:
    """A member of another team cannot read {team}'s prompt library. [username={username}]"""
    resp = cp(username).get(f"/teams/{fredlab_id}/prompts")
    assert resp.status_code in (403, 404), (
        f"{username} belongs to {USERS[username].teams}, not {TEST_TEAM}, yet read its prompts: "
        f"{resp.status_code} {resp.text[:200]}"
    )


def test_team_editor_can_update_and_score_prompt(fredlab_id, cp, created_prompt) -> None:
    """{editor} (team_editor of {team}) can update and score a team prompt."""
    editor = cp(FREDLAB_EDITORS[0])
    put_resp = editor.put(
        f"/teams/{fredlab_id}/prompts/{created_prompt['id']}",
        json={"name": created_prompt["name"], "text": "Say exactly: validation-ok-v2"},
    )
    assert put_resp.status_code == 200, (
        f"{FREDLAB_EDITORS[0]} could not update prompt {created_prompt['id']!r}: "
        f"{put_resp.status_code} {put_resp.text[:200]}"
    )
    score_resp = editor.patch(
        f"/teams/{fredlab_id}/prompts/{created_prompt['id']}", json={"score": 4.5}
    )
    assert score_resp.status_code == 200, (
        f"{FREDLAB_EDITORS[0]} could not score prompt {created_prompt['id']!r}: "
        f"{score_resp.status_code} {score_resp.text[:200]}"
    )


@pytest.mark.parametrize("username", FREDLAB_NON_EDITORS)
def test_non_editor_member_cannot_update_prompt(username: str, fredlab_id, cp, created_prompt) -> None:
    """A {team} member without team_editor cannot update a team prompt. [username={username}]"""
    resp = cp(username).put(
        f"/teams/{fredlab_id}/prompts/{created_prompt['id']}",
        json={"name": created_prompt["name"], "text": "should not be applied"},
    )
    assert resp.status_code == 403, (
        f"{username} is a member of {TEST_TEAM} but not team_editor, yet updated a prompt: "
        f"{resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.parametrize("username", FREDLAB_NON_EDITORS)
def test_non_editor_member_cannot_delete_prompt(username: str, fredlab_id, cp, created_prompt) -> None:
    """A {team} member without team_editor cannot delete a team prompt. [username={username}]"""
    resp = cp(username).delete(f"/teams/{fredlab_id}/prompts/{created_prompt['id']}")
    assert resp.status_code == 403, (
        f"{username} is a member of {TEST_TEAM} but not team_editor, yet deleted a prompt: "
        f"{resp.status_code} {resp.text[:200]}"
    )
    still_there = cp(FREDLAB_EDITORS[0]).get(f"/teams/{fredlab_id}/prompts/{created_prompt['id']}")
    assert still_there.status_code == 200, "prompt should still exist after the denied delete attempt"


def test_team_editor_can_promote_prompt_into_a_team_they_also_edit(
    fredlab_id, northbridge_id, cp, created_prompt
) -> None:
    """{editor}, editor of both {team} and northbridge, can promote a prompt between them."""
    editor = cp(FREDLAB_EDITORS[0])
    resp = editor.post(
        f"/teams/{fredlab_id}/prompts/{created_prompt['id']}/promote",
        json={"target_team_id": northbridge_id},
    )
    assert resp.status_code == 201, (
        f"{FREDLAB_EDITORS[0]} is team_editor of both {TEST_TEAM} and northbridge, but could not "
        f"promote a prompt between them: {resp.status_code} {resp.text[:200]}"
    )
    copy = resp.json()
    editor.delete(f"/teams/{northbridge_id}/prompts/{copy['id']}")


def test_team_editor_cannot_promote_prompt_into_a_team_with_no_relation(
    fredlab_id, swiftpost_id, cp, created_prompt
) -> None:
    """Review item 10: {editor}, editor of {team} only, cannot promote a prompt into swiftpost.

    Regression test for the review-item-10 finding: promoting used to only
    check the source team, letting a team_editor copy content into any
    target_team_id regardless of their relation there.
    """
    editor_username = FREDLAB_EDITORS[0]
    assert "swiftpost" not in USERS[editor_username].teams, (
        f"fixture assumption broken: {editor_username} now has a relation on swiftpost; "
        "pick a different fredlab-only editor for this negative test"
    )
    resp = cp(editor_username).post(
        f"/teams/{fredlab_id}/prompts/{created_prompt['id']}/promote",
        json={"target_team_id": swiftpost_id},
    )
    assert resp.status_code == 403, (
        f"{editor_username} holds no relation on swiftpost, yet promoting a {TEST_TEAM} prompt "
        f"into it returned {resp.status_code} {resp.text[:200]} - cross-team write bypass "
        f"(review item 10) has regressed."
    )
