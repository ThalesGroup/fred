# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

import pytest
from control_plane_backend.platform_access import api, service
from control_plane_backend.platform_access.schemas import CreatePlatformEnrollmentLink
from fastapi import FastAPI, HTTPException
from fred_core.security.platform_access.access_control import get_platform_access
from fred_core.security.platform_access.models import PlatformAccessLinkRow
from fred_core.security.rebac.rebac_engine import RelationType, TeamPermission
from fred_core.teams.team_metatada_models import TeamMetadataRow
from httpx import ASGITransport, AsyncClient
from test_platform_access import access as access_fixture
from test_platform_access import user

access = access_fixture


async def team_link(access, **body) -> str:
    return await service.generate_link(
        access, "demo", user("accepted"), CreatePlatformEnrollmentLink(**body), "team"
    )


@pytest.mark.asyncio
async def test_team_link_needs_no_free_flag_and_stays_out_of_free_history(access):
    token = await team_link(access, note="Workshop")
    team_page = await service.list_links(access, "demo", 0, 25, kind="team")
    assert team_page.total == 1 and team_page.items[0].status == "active"
    assert (await service.list_links(access, "demo", 0, 25)).total == 0
    assert (
        await service.list_links(access, "demo", 0, 25, "suspended", "team")
    ).total == 0
    link_id = team_page.items[0].id
    for operation in (
        lambda: service.reveal_link(access, "demo", link_id),
        lambda: service.revoke_link(access, "demo", link_id),
        lambda: service.list_link_joiners(access, "demo", link_id, 0, 25),
    ):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 404
    assert await service.reveal_link(access, "demo", link_id, "team") == token


@pytest.mark.asyncio
async def test_free_link_ids_are_unknown_to_the_team_family(access):
    actor = user("accepted")
    await service.set_team(access, actor, "demo", False, True)
    await service.generate_link(access, "demo", actor)
    free_id = (await service.list_links(access, "demo", 0, 25)).items[0].id
    with pytest.raises(HTTPException) as error:
        await service.revoke_link(access, "demo", free_id, "team")
    assert error.value.status_code == 404
    assert (await service.list_links(access, "demo", 0, 25, kind="team")).total == 0


@pytest.mark.asyncio
async def test_non_admitted_caller_is_refused_before_anything(access):
    actor = user("accepted")
    await access.observe(actor)
    # Even an authorized and Free team cannot admit through a team link.
    await service.set_team(access, actor, "demo", True, True)
    await service.set_filtering(access, actor, True)
    token = await team_link(access)
    outsider = user()
    for operation in (
        lambda: service.preview_link(access, outsider, token, None),
        lambda: service.record_opening(access, token, outsider),
        lambda: service.accept_cgu(access, outsider, token, "v1", "v1"),
        lambda: service.enroll(access, outsider, token, None),
    ):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert (error.value.status_code, error.value.detail) == (
            403,
            "platform_access_denied",
        )
    assert access.rebac.writes == []
    assert not await access.admitted(outsider)
    page = await service.list_links(access, "demo", 0, 25, kind="team")
    assert page.items[0].opening_count == 0
    joiners = await service.list_link_joiners(
        access, "demo", page.items[0].id, 0, 25, "team"
    )
    assert joiners.total == 0


@pytest.mark.asyncio
async def test_admitted_caller_joins_as_member_once(access, monkeypatch):
    events = []
    monkeypatch.setattr(
        service, "emit_audit_log", lambda name, **fields: events.append(name)
    )
    actor = user("accepted")
    await access.observe(actor)
    await service.set_filtering(access, actor, True)
    token = await team_link(access)
    newcomer = user("accepted")
    preview = await service.preview_link(access, newcomer, token, None)
    assert preview.team_name == "Demonstration"
    await service.record_opening(access, token, newcomer)
    await service.enroll(access, newcomer, token, None)
    await service.enroll(access, newcomer, token, None)
    assert [write.relation for write in access.rebac.writes] == [
        RelationType.TEAM_MEMBER
    ]
    assert access.rebac.writes[0].subject.id == newcomer.uid
    assert events == ["team.join_link.joined"]
    link_id = (await service.list_links(access, "demo", 0, 25, kind="team")).items[0].id
    joiners = await service.list_link_joiners(access, "demo", link_id, 0, 25, "team")
    assert [joiner.user_id for joiner in joiners.items] == [newcomer.uid]


@pytest.mark.asyncio
async def test_without_filtering_every_signed_in_person_can_join(access):
    token = await team_link(access)
    await service.enroll(access, user(), token, None)
    assert len(access.rebac.writes) == 1


@pytest.mark.asyncio
async def test_revoked_or_expired_team_links_are_invalid(access):
    revoked = await team_link(access)
    expired = await team_link(access)
    page = await service.list_links(access, "demo", 0, 25, kind="team")
    for item in page.items:
        if await service.reveal_link(access, "demo", item.id, "team") == revoked:
            await service.revoke_link(access, "demo", item.id, "team")
        else:
            async with access.store.mutation() as session:
                row = await session.get(PlatformAccessLinkRow, item.id)
                row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    for token in (revoked, expired):
        with pytest.raises(HTTPException) as error:
            await service.enroll(access, user(), token, None)
        assert error.value.status_code == 404
    assert await service.delete_inactive_links(access, "demo") == 0
    assert await service.delete_inactive_links(access, "demo", "team") == 2


@pytest.mark.asyncio
async def test_personal_team_is_refused(access):
    with pytest.raises(HTTPException):
        await service.generate_link(access, "personal-someone", user(), kind="team")


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
    async with access.store.mutation() as session:
        session.add(TeamMetadataRow(id="other", name="Other"))
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    caller = {"user": member}
    app.dependency_overrides[api.get_current_user] = lambda: caller["user"]
    base = "/teams/demo/join-links"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        link_id = "00000000-0000-0000-0000-000000000001"
        for method, path in (
            ("POST", base),
            ("GET", base),
            ("GET", f"{base}/{link_id}/joiners"),
            ("POST", f"{base}/{link_id}/reveal"),
            ("DELETE", f"{base}/{link_id}"),
            ("DELETE", f"{base}/inactive"),
        ):
            response = await client.request(
                method, path, json={} if method == "POST" else None
            )
            assert response.status_code == 403, path
        assert all(
            check == (TeamPermission.CAN_ADMINISTER_MEMBERS, "demo") for check in checks
        )
        caller["user"] = admin
        created = await client.post(base, json={"note": "Kick-off"})
        assert created.status_code == 200
        assert created.headers["cache-control"] == "no-store"
        listed = (await client.get(base)).json()
        assert listed["total"] == 1 and listed["items"][0]["note"] == "Kick-off"
        new_id = listed["items"][0]["id"]
        assert (await client.get("/teams/other/join-links")).json()["total"] == 0
        assert (
            await client.post(f"/teams/other/join-links/{new_id}/reveal")
        ).status_code == 404
        revealed = await client.post(f"{base}/{new_id}/reveal")
        assert revealed.json()["token"] == created.json()["token"]
        assert (await client.delete(f"{base}/{new_id}")).status_code == 204
        cleaned = await client.delete(f"{base}/inactive")
        assert cleaned.json() == {"deleted_count": 1}
    assert [name for name, _ in events] == [
        "platform.access.link.created",
        "platform.access.link.revealed",
        "platform.access.link.revoked",
        "platform.access.links.deleted",
    ]
    assert {fields["kind"] for _, fields in events} == {"team"}
    assert all(created.json()["token"] not in str(fields) for _, fields in events)
