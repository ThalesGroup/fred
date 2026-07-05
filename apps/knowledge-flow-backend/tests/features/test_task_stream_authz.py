# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Streaming a task's events is governed by the SAME rule as listing it (CTRLP-12):
creator, platform admin, or a team reader of the task's team. Parity with the
control-plane fix so 'visible in GET /tasks' and 'streamable' never diverge."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fred_core import AuthorizationError, KeycloakUser, TeamPermission
from fred_core.security.models import Resource

from knowledge_flow_backend.features.tasks.controller import _authorize_task_stream


def _user(uid: str = "u", roles: list[str] | None = None) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=None, roles=roles or [], groups=[])


def _run(*, created_by: str | None, team_id: str | None) -> Any:
    return SimpleNamespace(created_by=created_by, team_id=team_id)


class _FakeRebac:
    def __init__(self, *, platform: bool = False, team_ok: bool = False) -> None:
        self._platform = platform
        self._team_ok = team_ok
        self.team_checks: list[tuple[str, TeamPermission, str]] = []

    async def has_user_permission(self, user: KeycloakUser, permission: Any, resource_id: str, *, consistency_token: Any = None) -> bool:
        return self._platform

    async def check_user_team_permission_or_raise(self, user: KeycloakUser, permission: TeamPermission, team_id: str) -> str:
        self.team_checks.append((user.uid, permission, team_id))
        if not self._team_ok:
            raise AuthorizationError(user.uid, "read", Resource.TEAM, "denied")
        return "token"


@pytest.mark.asyncio
async def test_creator_may_stream() -> None:
    rebac = _FakeRebac()
    await _authorize_task_stream(_user("alice"), _run(created_by="alice", team_id="t1"), cast(Any, rebac))
    assert rebac.team_checks == []


@pytest.mark.asyncio
async def test_platform_admin_may_stream_another_users_task() -> None:
    rebac = _FakeRebac(platform=True)
    await _authorize_task_stream(_user("admin"), _run(created_by="alice", team_id="t1"), cast(Any, rebac))


@pytest.mark.asyncio
async def test_team_reader_may_stream_team_task() -> None:
    rebac = _FakeRebac(platform=False, team_ok=True)
    await _authorize_task_stream(_user("manager"), _run(created_by="alice", team_id="northbridge"), cast(Any, rebac))
    assert rebac.team_checks == [("manager", TeamPermission.CAN_READ_MEMEBERS, "northbridge")]


@pytest.mark.asyncio
async def test_non_reader_of_team_is_denied() -> None:
    rebac = _FakeRebac(platform=False, team_ok=False)
    with pytest.raises(AuthorizationError):
        await _authorize_task_stream(_user("bob"), _run(created_by="alice", team_id="northbridge"), cast(Any, rebac))


@pytest.mark.asyncio
async def test_no_team_non_platform_non_creator_is_denied() -> None:
    rebac = _FakeRebac(platform=False)
    with pytest.raises(HTTPException) as exc:
        await _authorize_task_stream(_user("bob"), _run(created_by="alice", team_id=None), cast(Any, rebac))
    assert exc.value.status_code == 403
