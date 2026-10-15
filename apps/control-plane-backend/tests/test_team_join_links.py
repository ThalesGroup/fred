# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from uuid import UUID

import pytest
from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.platform_access import api, service
from control_plane_backend.teams.schemas import UserTeamRelation
from fastapi import FastAPI, HTTPException
from fred_core.common import TeamId
from fred_core.security.platform_access.access_control import get_platform_access
from fred_core.security.rebac.rebac_engine import RelationType, TeamPermission
from httpx import ASGITransport, AsyncClient
from test_platform_access import MembershipEngine, draft, user
from test_platform_access import access as access_fixture
from tests.test_team_member_roles import _deps

access = access_fixture


async def enabled_token(access) -> str:
    link = await service.set_team_link(access, "demo", user("accepted"), True)
    assert link.enabled and link.token
    return link.token


async def refused(operation, status: int, detail: str) -> None:
    with pytest.raises(HTTPException) as error:
        await operation()
    assert (error.value.status_code, error.value.detail) == (status, detail)


@pytest.mark.asyncio
async def test_toggling_keeps_the_same_link(access):
    actor = user("accepted")
    initial = await service.get_team_link(access, "demo")
    assert (initial.enabled, initial.token) == (False, None)
    assert (await service.set_team_link(access, "demo", actor, False)).token is None
    token = await enabled_token(access)
    paused = await service.set_team_link(access, "demo", actor, False)
    assert (paused.enabled, paused.token) == (False, token)
    resumed = await service.set_team_link(access, "demo", actor, True)
    assert (resumed.enabled, resumed.token) == (True, token)
    assert (await service.get_team_link(access, "demo")).token == token


@pytest.mark.asyncio
async def test_paused_and_replaced_links_answer_invalid_link(access):
    actor, newcomer = user("accepted"), user("accepted")
    old = await enabled_token(access)
    await service.set_team_link(access, "demo", actor, False)
    for operation in (
        lambda: service.preview_link(access, newcomer, old, None),
        lambda: service.record_opening(access, old, newcomer),
        lambda: service.enroll(access, newcomer, old, None),
    ):
        await refused(operation, 404, "free_enrollment_link_invalid")
    new = (await service.regenerate_team_link(access, "demo", actor)).token
    assert new and new != old
    assert (await service.get_team_link(access, "demo")).enabled
    await refused(
        lambda: service.enroll(access, newcomer, old, None),
        404,
        "free_enrollment_link_invalid",
    )
    await service.enroll(access, newcomer, new, None)
    assert access.rebac.writes[0].subject.id == newcomer.uid


@pytest.mark.asyncio
async def test_non_admitted_caller_is_refused_before_any_effect(access):
    actor = user("accepted")
    await access.observe(actor)
    # Even an authorized and Free team cannot admit through a team link.
    await service.set_team(access, actor, "demo", True, True)
    await service.set_filtering(access, actor, True)
    token = await enabled_token(access)
    outsider = user()
    for operation in (
        lambda: service.preview_link(access, outsider, token, None),
        lambda: service.record_opening(access, token, outsider),
        lambda: service.accept_cgu(access, outsider, token, "v1", "v1"),
        lambda: service.enroll(access, outsider, token, None),
    ):
        await refused(operation, 403, "team_link_requires_platform_access")
    assert access.rebac.writes == []
    assert not await access.admitted(outsider)
    async with access.store.read() as session:
        link = await service.team_link(access, "demo", session)
        assert link is not None and link.opening_count == 0


@pytest.mark.asyncio
async def test_admitted_caller_joins_as_member_once(access, monkeypatch):
    events = []
    monkeypatch.setattr(
        service, "emit_audit_log", lambda name, **fields: events.append(name)
    )
    actor = user("accepted")
    await access.observe(actor)
    await service.set_filtering(access, actor, True)
    token = await enabled_token(access)
    newcomer = user("accepted")
    preview = await service.preview_link(access, newcomer, token, None)
    assert preview.team_name == "Demonstration"
    joined = await service.enroll(access, newcomer, token, None)
    again = await service.enroll(access, newcomer, token, None)
    # Both the join and the already-member retry let the page open the team.
    assert joined.team_id == again.team_id == "demo"
    assert [write.relation for write in access.rebac.writes] == [
        RelationType.TEAM_MEMBER
    ]
    assert events == ["team.join_link.joined"]


@pytest.mark.asyncio
async def test_without_filtering_every_signed_in_person_can_join(access):
    token = await enabled_token(access)
    await service.enroll(access, user(), token, None)
    assert len(access.rebac.writes) == 1


@pytest.mark.asyncio
async def test_team_link_stays_out_of_free_link_administration(access):
    actor = user("accepted")
    await enabled_token(access)
    async with access.store.read() as session:
        link = await service.team_link(access, "demo", session)
        assert link is not None
    assert (await service.list_links(access, "demo", 0, 25)).total == 0
    for operation in (
        lambda: service.reveal_link(access, "demo", link.id),
        lambda: service.revoke_link(access, "demo", link.id),
        lambda: service.list_link_joiners(access, "demo", link.id, 0, 25),
    ):
        await refused(operation, 404, "free_enrollment_link_invalid")
    await service.set_team(access, actor, "demo", False, True)
    await service.generate_link(access, "demo", actor)
    await service.regenerate_team_link(access, "demo", actor)
    assert (await service.list_links(access, "demo", 0, 25)).total == 1
    assert (await service.get_team_link(access, "demo")).enabled


@pytest.mark.asyncio
async def test_personal_team_is_refused(access):
    with pytest.raises(HTTPException):
        await service.set_team_link(access, "personal-someone", user(), True)


@pytest.mark.asyncio
async def test_routes_require_team_member_administration(access, monkeypatch):
    admin, member = user("accepted"), user("accepted")
    checks = []

    async def check(subject, permission, resource_id, **kwargs):
        checks.append((permission, resource_id))
        if subject.uid != admin.uid:
            raise HTTPException(403, "forbidden")

    monkeypatch.setattr(access.rebac, "check_user_permission_or_raise", check)
    events = []
    monkeypatch.setattr(
        api, "emit_audit_log", lambda name, **fields: events.append((name, fields))
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[get_application_configuration] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version=None)
    )
    caller = {"user": member}
    app.dependency_overrides[api.get_current_user] = lambda: caller["user"]
    app.dependency_overrides[api.get_own_user_for_platform_access] = lambda: caller[
        "user"
    ]
    base = "/teams/demo/join-link"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for method, path, body in (
            ("GET", base, None),
            ("PUT", base, {"enabled": True}),
            ("POST", f"{base}/regenerate", None),
        ):
            response = await client.request(method, path, json=body)
            assert response.status_code == 403, path
        assert set(checks) == {(TeamPermission.CAN_ADMINISTER_MEMBERS, "demo")}
        caller["user"] = admin
        enabled = await client.put(base, json={"enabled": True})
        assert enabled.status_code == 200
        assert enabled.headers["cache-control"] == "no-store"
        token = enabled.json()["token"]
        state = await client.get(base)
        assert state.json() == {"enabled": True, "token": token}
        assert state.headers["cache-control"] == "no-store"
        paused = await client.put(base, json={"enabled": False})
        assert paused.json() == {"enabled": False, "token": token}
        regenerated = (await client.post(f"{base}/regenerate")).json()
        assert regenerated["enabled"] and regenerated["token"] != token
        admin.service_account = True
        assert (await client.get(base)).status_code == 403
        admin.service_account = False

        # A person without platform access learns nothing about the team.
        await access.observe(admin)
        await service.set_filtering(access, admin, True)
        caller["user"] = user()
        denied = await client.get(f"/platform-access/free/{regenerated['token']}")
        assert denied.status_code == 403
        assert denied.json() == {"detail": "team_link_requires_platform_access"}
        assert "Demonstration" not in denied.text
    assert [name for name, _ in events] == [
        "team.join_link.enabled",
        "team.join_link.paused",
        "team.join_link.regenerated",
    ]
    assert all(token not in str(fields) for _, fields in events)


async def admin_with_exception(access):
    actor = user("accepted")
    await access.observe(actor)
    await service.set_user(access, actor, UUID(actor.uid), True)
    await service.set_filtering(access, actor, True)
    return actor


def team_sources(page, uid):
    row = next(item for item in page.items if item.user_id == uid)
    return {(source.kind, source.team_id) for source in row.sources}


@pytest.mark.asyncio
async def test_team_link_member_of_free_team_loses_access_when_the_rule_tightens(
    access,
):
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", False, True)
    member = user("accepted")
    await service.enroll(access, member, await enabled_token(access), None)
    assert "demo" in access.rebac.members[member.uid]
    assert await access.admitted(member)
    assert team_sources(await service.users_page(access, 0, 25, ""), member.uid) == {
        ("attribute", None)
    }
    await service.save_policy(access, actor, draft("tightened"), 1)
    assert not await access.admitted(member)
    preview = await service.activation_preview(access)
    row = next(item for item in preview.users if item.user_id == member.uid)
    assert (row.outcome, row.sources) == ("blocked", [])


@pytest.mark.asyncio
async def test_free_link_joiner_keeps_access_only_while_member_and_free(access):
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", False, True)
    joiner = user()
    await service.enroll(
        access, joiner, await service.generate_link(access, "demo", actor), None
    )
    assert await access.admitted(joiner)
    assert team_sources(await service.users_page(access, 0, 25, ""), joiner.uid) == {
        ("free", "demo")
    }
    preview = await service.activation_preview(access)
    row = next(item for item in preview.users if item.user_id == joiner.uid)
    assert row.outcome == "allowed"
    assert [(s.kind, s.team_id) for s in row.sources] == [("free", "demo")]
    await service.set_team(access, actor, "demo", False, False)
    assert not await access.admitted(joiner)
    await service.set_team(access, actor, "demo", False, True)
    assert await access.admitted(joiner)


class RemovableMembers(MembershipEngine):
    """Membership double whose removal goes through the real teams service."""

    async def delete_relations(self, relations):
        for relation in relations:
            self.members.get(relation.subject.id, set()).discard(relation.resource.id)


async def remove_from_demo(access, monkeypatch, actor, person) -> None:
    from control_plane_backend.scheduler.policies.policy_models import (
        ConversationPolicyCatalog,
    )
    from control_plane_backend.teams import service as teams_service
    from fred_core.security.platform_access import access_control

    class NoSessions:
        async def get_for_user(self, *args):
            return []

    monkeypatch.setattr(access_control, "_available", True)
    monkeypatch.setattr(access_control, "_installed", access)
    monkeypatch.setattr(teams_service, "_get_user_roles_in_team", _member_roles)
    monkeypatch.setattr(teams_service, "_validate_team_and_check_permission", _no_check)
    deps = _deps(
        access.rebac,
        "demo",
        get_session_store=NoSessions,
        get_purge_queue_store=object,
        get_policy_catalog=ConversationPolicyCatalog,
    )
    await teams_service.remove_team_member(actor, TeamId("demo"), person.uid, deps)


async def _member_roles(*args, **kwargs):
    return {UserTeamRelation.TEAM_MEMBER}


async def _no_check(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_removed_free_joiner_re_added_by_hand_stays_refused(access, monkeypatch):
    access.rebac = RemovableMembers()
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", False, True)
    joiner = user()
    await service.enroll(
        access, joiner, await service.generate_link(access, "demo", actor), None
    )
    link_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    await service.revoke_link(access, "demo", link_id)
    await remove_from_demo(access, monkeypatch, actor, joiner)
    assert not await access.admitted(joiner)
    assert (await service.list_link_joiners(access, "demo", link_id, 0, 25)).total == 0
    # A team admin adds them back by hand: no Free source comes back.
    access.rebac.members[joiner.uid].add("demo")
    assert not await access.admitted(joiner)


@pytest.mark.asyncio
async def test_removed_free_joiner_regains_access_by_enrolling_again(
    access, monkeypatch
):
    access.rebac = RemovableMembers()
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", False, True)
    token = await service.generate_link(access, "demo", actor)
    joiner = user()
    await service.enroll(access, joiner, token, None)
    await remove_from_demo(access, monkeypatch, actor, joiner)
    assert not await access.admitted(joiner)
    await service.enroll(access, joiner, token, None)
    assert await access.admitted(joiner)


@pytest.mark.asyncio
async def test_member_added_by_hand_to_a_free_team_gets_no_access_source(access):
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", False, True)
    added = user()
    await access.observe(added)
    access.rebac.members[added.uid] = {"demo"}
    assert not await access.admitted(added)
    assert team_sources(await service.users_page(access, 0, 25, ""), added.uid) == set()


@pytest.mark.asyncio
async def test_authorized_team_still_admits_every_member(access):
    actor = await admin_with_exception(access)
    await service.set_team(access, actor, "demo", True, True)
    member = user("accepted")
    await service.enroll(access, member, await enabled_token(access), None)
    await service.save_policy(access, actor, draft("tightened"), 1)
    assert await access.admitted(member)
    assert team_sources(await service.users_page(access, 0, 25, ""), member.uid) == {
        ("team", "demo")
    }
