# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Runtime authorization validation against a RUNNING Fred platform.

Design goal: a failing run is understood in one minute, without reading Fred.
Every scenario names the concrete actor, team, and agent; every failure says what
was expected, what happened, and what to do.

What it checks under the no-grant model:
  1. ReBAC membership - each user sees exactly their teams (no leakage).
  2. The test agent is visible/deployable in the catalog.
  3. prepare-execution is team-scoped: members can prepare, non-members cannot.
  4. Runtime execution is pod-side authorized: members can stream, non-members
     who bypass prepare-execution and call the pod directly are denied.
  5. Enroll authorization: a plain member cannot enroll in a collaborative team;
     a user can self-service enroll in their own personal space.

The concrete agent and team are a single source of truth in factory_config
(TEST_AGENT_ID / TEST_TEAM). Change them there and every name + message follows.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from urllib.parse import urljoin

import httpx
import pytest
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.execution import RuntimeExecuteRequest

from factory_config import (
    AGENT_TAG,
    RUNTIME_PUBLIC_BASE,
    TEAM_OPERATOR_USERNAME,
    TEST_AGENT_ID,
    TEST_TEAM,
    USERS,
)


def _identifiers(team_item: dict) -> set[str]:
    """Accept either {'id': ...} or {'name': ...} shapes for a team."""
    return {str(team_item.get(k)) for k in ("id", "name", "team_id") if team_item.get(k)}


MEMBERS = sorted(u for u, fu in USERS.items() if TEST_TEAM in fu.teams)
NON_MEMBERS = sorted(u for u, fu in USERS.items() if TEST_TEAM not in fu.teams)
PLAIN_MEMBERS = sorted(u for u in MEMBERS if not USERS[u].can_enroll_in(TEST_TEAM))
TEAM_ADMINS = sorted(u for u in MEMBERS if USERS[u].is_team_admin_in(TEST_TEAM))
TEAM_EDITORS = sorted(u for u in MEMBERS if USERS[u].is_team_editor_in(TEST_TEAM))
IDENTITY_ONLY_USERNAMES = sorted(
    u for u, fu in USERS.items() if not fu.teams and not fu.app_roles and not fu.platform_roles
)



def _json_or_text(resp: httpx.Response) -> object:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 - diagnostics only
        return resp.text[:400]


def _sse_events(resp: httpx.Response) -> Iterator[dict]:
    """Parse small Fred SSE responses into JSON event dictionaries."""
    data_lines: list[str] = []
    for line in resp.iter_lines():
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                data_lines.clear()
                if raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError as exc:
                    pytest.fail(f"Invalid SSE JSON frame: {raw!r} ({exc})", pytrace=False)
                if isinstance(event, dict):
                    yield event
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    if data_lines:
        raw = "\n".join(data_lines)
        if raw != "[DONE]":
            event = json.loads(raw)
            if isinstance(event, dict):
                yield event


def _runtime_url(path: str) -> str:
    """Resolve an ingress-relative runtime URL against the configured public runtime origin."""
    return urljoin(RUNTIME_PUBLIC_BASE, path)


def _jwt_sub(token: str) -> str:
    """Extract the Keycloak subject from a JWT without verifying it; validation already obtained it from Keycloak."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    subject = str(decoded.get("sub") or "")
    assert subject, "Keycloak token has no sub claim"
    return subject


# --- 1. ReBAC team membership (per user) -------------------------------------


@pytest.mark.parametrize("username", sorted(USERS))
def test_user_sees_exactly_their_teams(username: str, cp, users) -> None:
    """Check that a user sees exactly their own teams and no other team leaks (ReBAC isolation)."""
    user = users[username]
    resp = cp(username).get("/teams")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list), f"unexpected /teams shape: {items!r}"
    collaborative = [t for t in items if not str(t.get("id", "")).startswith("personal-")]
    seen: set[str] = set().union(*[_identifiers(t) for t in collaborative]) if collaborative else set()
    for team in user.teams:
        assert team in seen, f"{username} should see team {team!r}; got {sorted(seen)}"
    assert len(collaborative) == len(user.teams), (
        f"{username}: expected collaborative teams {sorted(user.teams)}, "
        f"got {[t.get('name') for t in collaborative]}"
    )


# --- 2. Resolve the team + the one test agent --------------------------------


def _resolve_team_id(admin) -> str:
    if TEAM_OPERATOR_USERNAME is None:
        pytest.fail(
            f"No user in configuration.yaml can administer/enroll in {TEST_TEAM!r}; "
            f"grant team_admin/team_editor (Swift) or owner/manager (Kea) to one fixture user.",
            pytrace=False,
        )
    teams = admin.get("/teams").json()
    by_name = {t.get("name"): t for t in teams}
    item = by_name.get(TEST_TEAM)
    if item is None:
        pytest.fail(
            f"Test team {TEST_TEAM!r} is not visible to the configured team operator in /teams.\n"
            f"Teams returned: {sorted(n for n in by_name if n)}\n"
            f"-> Is configuration.yaml seeded (make docker-up)? Did the team get "
            f"renamed? Update TEST_TEAM in factory_config.py if so.",
            pytrace=False,
        )
    return str(item.get("id") or item.get("name"))


def _resolve_test_template(admin) -> tuple[str, dict]:
    team_id = _resolve_team_id(admin)
    resp = admin.get(f"/teams/{team_id}/agent-templates")
    if resp.status_code != 200:
        pytest.fail(
            f"GET /teams/{team_id}/agent-templates -> {resp.status_code}: "
            f"{resp.text[:160]}\n-> This is a complete-stack validation: the runtime catalog must be reachable.",
            pytrace=False,
        )
    catalog = resp.json()
    if not catalog:
        pytest.fail(
            f"{TEST_TEAM!r}'s agent catalog is empty - no runtime templates.\n"
            f"-> This is a complete-stack validation: start the runtime pod(s) and "
            f"register the runtime catalog source on the control-plane.",
            pytrace=False,
        )
    visible = sorted(t.get("source_agent_id", "?") for t in catalog)
    template = next((t for t in catalog if t.get("source_agent_id") == TEST_AGENT_ID), None)
    if template is None:
        pytest.fail(
            f"Expected test agent {AGENT_TAG} is not in {TEST_TEAM!r}'s visible catalog.\n"
            f"Visible agents ({len(visible)}): {visible}\n"
            f"-> Either deploy that agent in fred-agents, or fix TEST_AGENT_ID in "
            f"factory_config.py if it was renamed. (We match on source_agent_id.)",
            pytrace=False,
        )
    return team_id, template


def test_expected_test_agent_is_visible_in_catalog(cp) -> None:
    """Check that the configured test agent is visible and deployable in the team catalog."""
    assert TEAM_OPERATOR_USERNAME is not None
    _team_id, template = _resolve_test_template(cp(TEAM_OPERATOR_USERNAME))
    assert template.get("template_id"), f"{AGENT_TAG} template has no template_id: {template!r}"


@pytest.fixture(scope="module")
def enrolled_agent(cp):
    """Enroll the test agent into the test team as the configured team operator, yield its ids, clean up after."""
    assert TEAM_OPERATOR_USERNAME is not None
    admin = cp(TEAM_OPERATOR_USERNAME)
    team_id, template = _resolve_test_template(admin)
    template_id = template["template_id"]

    name = f"val-{uuid.uuid4().hex[:8]}"
    created = admin.post(
        f"/teams/{team_id}/agent-instances",
        json={"template_id": template_id, "display_name": name},
    )
    assert created.status_code in (200, 201), (
        f"Team operator ({TEAM_OPERATOR_USERNAME}) could not enroll {AGENT_TAG} into {TEST_TEAM!r}: "
        f"{created.status_code} {created.text[:200]}"
    )
    instance_id = created.json().get("agent_instance_id") or created.json().get("id")
    assert instance_id, f"enroll response has no instance id: {created.text[:400]}"

    yield {"team_id": team_id, "instance_id": instance_id, "template_id": template_id}

    admin.delete(f"/teams/{team_id}/agent-instances/{instance_id}")


# --- 3. prepare-execution matrix ---------------------------------------------


def _prepare(client, team_id: str, instance_id: str) -> httpx.Response:
    return client.post(f"/teams/{team_id}/agent-instances/{instance_id}/prepare-execution")


@pytest.mark.parametrize("username", MEMBERS)
def test_member_can_prepare_runtime_execution(username: str, enrolled_agent, cp) -> None:
    """A member of the test team can prepare execution without receiving any grant."""
    resp = _prepare(cp(username), enrolled_agent["team_id"], enrolled_agent["instance_id"])
    assert resp.status_code == 200, (
        f"{username} (member of {TEST_TEAM}) was refused prepare-execution for {AGENT_TAG}: "
        f"{resp.status_code} {resp.text[:200]}"
    )
    payload = resp.json()
    assert "execution_grant" not in payload, (
        "prepare-execution must not return a signed capability in the no-grant model: "
        f"{payload!r}"
    )
    assert payload.get("execute_stream_url"), f"prepare response has no stream URL: {payload!r}"
    assert str(payload["execute_stream_url"]).startswith("/"), (
        "runtime URL must be ingress-relative, not a cluster-internal hostname: "
        f"{payload['execute_stream_url']!r}"
    )


@pytest.mark.parametrize("username", NON_MEMBERS)
def test_non_member_is_denied_prepare_execution(username: str, enrolled_agent, cp) -> None:
    """A non-member of the test team is denied prepare-execution."""
    resp = _prepare(cp(username), enrolled_agent["team_id"], enrolled_agent["instance_id"])
    assert resp.status_code in (403, 404), (
        f"{username} is not a member of {TEST_TEAM} yet prepared execution for {AGENT_TAG} "
        f"(status {resp.status_code}) - cross-team isolation breach. Body: {resp.text[:200]}"
    )


# --- 4. Runtime pod-side authorization ---------------------------------------


def _runtime_execute_stream(
    *,
    token: str,
    execute_stream_url: str,
    agent_instance_id: str,
    team_id: str,
    input_text: str = "Say exactly: validation-ok",
    forged_user_id: str | None = None,
) -> httpx.Response:
    runtime_context = RuntimeContext(team_id=team_id)
    if forged_user_id is not None:
        runtime_context = runtime_context.model_copy(update={"user_id": forged_user_id})
    request = RuntimeExecuteRequest(
        agent_instance_id=agent_instance_id,
        input=input_text,
        session_id=f"val-{uuid.uuid4().hex}",
        runtime_context=runtime_context,
    )
    url = _runtime_url(execute_stream_url)
    return httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
        },
        json=request.model_dump(mode="json"),
        timeout=30.0,
    )


def _prepared_stream_url(username: str, enrolled_agent, cp) -> str:
    resp = _prepare(cp(username), enrolled_agent["team_id"], enrolled_agent["instance_id"])
    assert resp.status_code == 200, f"prepare failed for {username}: {resp.status_code} {resp.text[:200]}"
    return str(resp.json()["execute_stream_url"])


def test_member_can_execute_runtime_stream_with_keycloak_jwt(enrolled_agent, token_for, cp) -> None:
    """A real team member can execute the runtime SSE stream with their Keycloak JWT."""
    username = MEMBERS[0]
    execute_stream_url = _prepared_stream_url(username, enrolled_agent, cp)
    resp = _runtime_execute_stream(
        token=token_for(username),
        execute_stream_url=execute_stream_url,
        agent_instance_id=enrolled_agent["instance_id"],
        team_id=enrolled_agent["team_id"],
    )
    assert resp.status_code == 200, (
        f"{username} could prepare execution but runtime rejected the JWT/SSE call "
        f"to {resp.request.url}: {resp.status_code} {resp.text[:400]}"
    )
    events = list(_sse_events(resp))
    event_kinds = {str(e.get("kind") or e.get("type")) for e in events}
    assert event_kinds & {"final", "awaiting_human"}, (
        f"runtime stream did not complete as expected for {username}; events={events!r}"
    )


@pytest.mark.parametrize("username", NON_MEMBERS)
def test_non_member_cannot_bypass_prepare_by_calling_runtime_directly(username: str, enrolled_agent, token_for, cp) -> None:
    """A non-member cannot call the runtime pod directly using another team's team_id."""
    member = MEMBERS[0]
    execute_stream_url = _prepared_stream_url(member, enrolled_agent, cp)
    resp = _runtime_execute_stream(
        token=token_for(username),
        execute_stream_url=execute_stream_url,
        agent_instance_id=enrolled_agent["instance_id"],
        team_id=enrolled_agent["team_id"],
    )
    assert resp.status_code in (401, 403, 404), (
        f"{username} is not a member of {TEST_TEAM} but the runtime accepted a direct "
        f"pod call for {AGENT_TAG}: url={resp.request.url} "
        f"status={resp.status_code} body={resp.text[:400]}"
    )


def test_runtime_ignores_forged_context_user_id(enrolled_agent, token_for, cp) -> None:
    """A forged runtime_context.user_id must not become the authenticated runtime identity."""
    username = MEMBERS[0]
    execute_stream_url = _prepared_stream_url(username, enrolled_agent, cp)
    resp = _runtime_execute_stream(
        token=token_for(username),
        execute_stream_url=execute_stream_url,
        agent_instance_id=enrolled_agent["instance_id"],
        team_id=enrolled_agent["team_id"],
        forged_user_id="mallory",
    )
    assert resp.status_code == 200, (
        "runtime should derive identity from the JWT, not trust runtime_context.user_id; "
        f"url={resp.request.url} status={resp.status_code} body={resp.text[:400]}"
    )


# --- 5. Enroll matrix ---------------------------------------------------------


@pytest.mark.parametrize("username", PLAIN_MEMBERS)
def test_plain_member_cannot_enroll_agent_in_collaborative_team(username: str, cp) -> None:
    """A plain team member cannot enroll an agent in the collaborative test team."""
    assert TEAM_OPERATOR_USERNAME is not None
    operator = cp(TEAM_OPERATOR_USERNAME)
    team_id, template = _resolve_test_template(operator)
    resp = cp(username).post(
        f"/teams/{team_id}/agent-instances",
        json={"template_id": template["template_id"], "display_name": f"deny-{uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code in (403, 404), (
        f"{username} unexpectedly enrolled {AGENT_TAG} into {TEST_TEAM}: "
        f"{resp.status_code} {_json_or_text(resp)!r}"
    )


@pytest.mark.parametrize("username", TEAM_ADMINS)
def test_team_admin_cannot_enroll_agent_without_editor_role(username: str, cp) -> None:
    """A team_admin without team_editor cannot enroll an agent in the collaborative test team."""
    if USERS[username].is_team_editor_in(TEST_TEAM):
        pytest.skip(f"{username} also has editor authority in {TEST_TEAM}; not a split-role fixture")
    assert TEAM_OPERATOR_USERNAME is not None
    operator = cp(TEAM_OPERATOR_USERNAME)
    team_id, template = _resolve_test_template(operator)
    resp = cp(username).post(
        f"/teams/{team_id}/agent-instances",
        json={
            "template_id": template["template_id"],
            "display_name": f"deny-admin-{uuid.uuid4().hex[:6]}",
        },
    )
    instance_id = None
    if resp.status_code in (200, 201):
        instance_id = resp.json().get("agent_instance_id") or resp.json().get("id")
        if instance_id:
            operator.delete(f"/teams/{team_id}/agent-instances/{instance_id}")
    assert resp.status_code in (403, 404), (
        f"{username} is team_admin of {TEST_TEAM} but not team_editor, yet enrolled {AGENT_TAG}: "
        f"{resp.status_code} {_json_or_text(resp)!r}"
    )


@pytest.mark.parametrize("username", TEAM_EDITORS)
def test_team_editor_cannot_administer_members_without_admin_role(username: str, cp, token_for) -> None:
    """A team_editor without team_admin cannot add members to the collaborative test team."""
    if USERS[username].is_team_admin_in(TEST_TEAM):
        pytest.skip(f"{username} also has admin authority in {TEST_TEAM}; not a split-role fixture")
    assert TEAM_OPERATOR_USERNAME is not None
    assert IDENTITY_ONLY_USERNAMES, "Need at least one identity-only user outside the test team"
    operator = cp(TEAM_OPERATOR_USERNAME)
    team_id = _resolve_team_id(operator)
    target_username = IDENTITY_ONLY_USERNAMES[0]
    target_user_id = _jwt_sub(token_for(target_username))
    resp = cp(username).post(
        f"/teams/{team_id}/members",
        json={"user_id": target_user_id, "relation": "team_member"},
    )
    if resp.status_code in (200, 201, 202, 204):
        operator.delete(f"/teams/{team_id}/members/{target_user_id}")
    assert resp.status_code in (403, 404), (
        f"{username} is team_editor of {TEST_TEAM} but not team_admin, yet added {target_username}: "
        f"{resp.status_code} {_json_or_text(resp)!r}"
    )


@pytest.mark.parametrize("username", sorted(USERS))
def test_user_can_enroll_agent_in_their_personal_team(username: str, cp) -> None:
    """Each user can enroll the public test agent in their own personal space."""
    client = cp(username)
    teams = client.get("/teams").json()
    personal = next((t for t in teams if str(t.get("id", "")).startswith("personal-")), None)
    if personal is None:
        pytest.fail(f"{username} has no personal-* team returned by /teams", pytrace=False)
    personal_id = str(personal.get("id") or personal.get("name"))
    resp = client.get(f"/teams/{personal_id}/agent-templates")
    if resp.status_code != 200:
        pytest.fail(
            f"{username}: cannot list personal templates: {resp.status_code} {resp.text[:160]}",
            pytrace=False,
        )
    template = next((t for t in resp.json() if t.get("source_agent_id") == TEST_AGENT_ID), None)
    if template is None:
        pytest.fail(
            f"{username}: {AGENT_TAG} is not available in personal catalog",
            pytrace=False,
        )

    name = f"personal-val-{uuid.uuid4().hex[:6]}"
    created = client.post(
        f"/teams/{personal_id}/agent-instances",
        json={"template_id": template["template_id"], "display_name": name},
    )
    assert created.status_code in (200, 201), (
        f"{username} could not enroll {AGENT_TAG} in their personal team: "
        f"{created.status_code} {created.text[:200]}"
    )
    instance_id = created.json().get("agent_instance_id") or created.json().get("id")
    if instance_id:
        client.delete(f"/teams/{personal_id}/agent-instances/{instance_id}")
