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

"""Regression coverage for #2148: `get_users_by_ids` backs the admin-display
enrichment `_enrich_teams_with_membership` calls with every distinct team
admin id on every bootstrap/teams load — one Keycloak Admin REST
`a_get_user` call per id, uncached, was the second (Keycloak-side) fan-out
found alongside the OpenFGA one #2065/#2145 already addressed. This file
proves the added 5-minute TTL cache actually avoids repeat Keycloak calls,
including for the 404/"unknown user" fallback path.
"""

from __future__ import annotations

import time as time_module
from typing import Any, cast

import pytest
from control_plane_backend.users import service as users_service
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.service import get_users_by_ids
from keycloak.exceptions import KeycloakGetError


class _FakeKeycloakAdmin:
    def __init__(self, users: dict[str, dict]) -> None:
        self._users = users
        self.calls: list[str] = []

    async def a_get_user(self, user_id: str) -> dict:
        self.calls.append(user_id)
        if user_id not in self._users:
            raise KeycloakGetError(error_message="not found", response_code=404)
        return self._users[user_id]


def _deps(admin: _FakeKeycloakAdmin) -> UserServiceDependencies:
    return UserServiceDependencies(
        configuration=cast(Any, object()),
        create_keycloak_admin_client=cast(Any, lambda: admin),
    )


@pytest.mark.asyncio
async def test_get_users_by_ids_serves_repeat_calls_from_cache() -> None:
    admin = _FakeKeycloakAdmin(
        {
            "u-1": {"id": "u-1", "username": "alice"},
            "u-2": {"id": "u-2", "username": "bob"},
        }
    )
    deps = _deps(admin)

    first = await get_users_by_ids(["u-1", "u-2"], deps)
    assert {uid: s.username for uid, s in first.items()} == {
        "u-1": "alice",
        "u-2": "bob",
    }
    assert sorted(admin.calls) == ["u-1", "u-2"]

    second = await get_users_by_ids(["u-1", "u-2"], deps)
    assert {uid: s.username for uid, s in second.items()} == {
        "u-1": "alice",
        "u-2": "bob",
    }
    assert sorted(admin.calls) == ["u-1", "u-2"], (
        "second call within the TTL window must be served entirely from cache"
    )


@pytest.mark.asyncio
async def test_get_users_by_ids_caches_404_fallback() -> None:
    """A deleted/unknown admin id must not re-hit Keycloak on every bootstrap
    either — the `UserSummary(id=...)` fallback is cached the same as a real
    hit."""
    admin = _FakeKeycloakAdmin({})
    deps = _deps(admin)

    first = await get_users_by_ids(["ghost"], deps)
    assert first["ghost"].id == "ghost"
    assert admin.calls == ["ghost"]

    second = await get_users_by_ids(["ghost"], deps)
    assert second["ghost"].id == "ghost"
    assert admin.calls == ["ghost"], "404 fallback must be cached too"


@pytest.mark.asyncio
async def test_get_users_by_ids_refetches_after_ttl_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _FakeKeycloakAdmin({"u-1": {"id": "u-1", "username": "alice"}})
    deps = _deps(admin)

    fake_now = 2_000_000.0
    monkeypatch.setattr(time_module, "time", lambda: fake_now)

    await get_users_by_ids(["u-1"], deps)
    assert admin.calls == ["u-1"]

    # still within the 5-minute TTL: cache hit, no new call
    fake_now += users_service._USER_SUMMARY_CACHE_TTL_SECONDS - 1
    await get_users_by_ids(["u-1"], deps)
    assert admin.calls == ["u-1"]

    # past the TTL: must re-fetch
    fake_now += 2
    await get_users_by_ids(["u-1"], deps)
    assert admin.calls == ["u-1", "u-1"]


@pytest.mark.asyncio
async def test_get_users_by_ids_only_fetches_uncached_ids() -> None:
    """A partially-warm cache must only fetch the miss, not the whole batch —
    the common case once a few admins recur across many teams."""
    admin = _FakeKeycloakAdmin(
        {
            "u-1": {"id": "u-1", "username": "alice"},
            "u-2": {"id": "u-2", "username": "bob"},
        }
    )
    deps = _deps(admin)

    await get_users_by_ids(["u-1"], deps)
    assert admin.calls == ["u-1"]

    result = await get_users_by_ids(["u-1", "u-2"], deps)
    assert admin.calls == ["u-1", "u-2"]
    assert {uid: s.username for uid, s in result.items()} == {
        "u-1": "alice",
        "u-2": "bob",
    }
