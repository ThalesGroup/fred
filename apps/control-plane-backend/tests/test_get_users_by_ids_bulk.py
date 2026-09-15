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

"""`get_users_by_ids` resolves many cache misses with as few Keycloak calls as
the realm size allows: a paged directory scan when it is cheaper than one
`a_get_user` per id, a bounded per-id fan-out otherwise. Ids are unique per
test so the module-level summary cache never leaks between them."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from control_plane_backend.users import service as users_service
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.service import get_users_by_ids
from keycloak.exceptions import KeycloakGetError


class _FakeKeycloakAdmin:
    def __init__(
        self,
        users: dict[str, dict],
        *,
        listed_ids: set[str] | None = None,
        total_users: int | None = None,
    ) -> None:
        self._users = users
        # What the paged listing returns; Keycloak leaves service accounts out.
        self._listed = sorted(listed_ids if listed_ids is not None else users)
        self._total_users = (
            total_users if total_users is not None else len(self._listed)
        )
        self.get_user_calls: list[str] = []
        self.page_queries: list[dict] = []
        self.count_calls = 0
        self._in_flight = 0
        self.max_in_flight = 0

    async def a_users_count(self) -> int:
        self.count_calls += 1
        return self._total_users

    async def a_get_users(self, query: dict) -> list[dict]:
        self.page_queries.append(query)
        first, size = query["first"], query["max"]
        return [self._users[uid] for uid in self._listed[first : first + size]]

    async def a_get_user(self, user_id: str) -> dict:
        self.get_user_calls.append(user_id)
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(0)
            if user_id not in self._users:
                raise KeycloakGetError(error_message="not found", response_code=404)
            return self._users[user_id]
        finally:
            self._in_flight -= 1


def _users(prefix: str, count: int) -> dict[str, dict]:
    return {
        f"{prefix}-{i:04d}": {"id": f"{prefix}-{i:04d}", "username": f"{prefix}{i}"}
        for i in range(count)
    }


def _deps(admin: _FakeKeycloakAdmin) -> UserServiceDependencies:
    return UserServiceDependencies(
        configuration=cast(Any, object()),
        create_keycloak_admin_client=cast(Any, lambda: admin),
    )


@pytest.mark.asyncio
async def test_many_misses_read_the_directory_by_pages_when_cheaper() -> None:
    users = _users("scan", 250)
    admin = _FakeKeycloakAdmin(users)
    wanted = sorted(users)[:60]

    result = await get_users_by_ids(wanted, _deps(admin))

    assert admin.get_user_calls == []
    assert [query["first"] for query in admin.page_queries] == [
        0,
        users_service._USER_PAGE_SIZE,
    ]
    assert {uid: summary.username for uid, summary in result.items()} == {
        uid: users[uid]["username"] for uid in wanted
    }

    admin.page_queries.clear()
    await get_users_by_ids(wanted, _deps(admin))
    assert admin.page_queries == []
    assert admin.get_user_calls == []


@pytest.mark.asyncio
async def test_ids_missing_from_the_scan_are_looked_up_one_by_one() -> None:
    users = _users("svc", 40)
    service_account = "svc-0000"
    admin = _FakeKeycloakAdmin(users, listed_ids=set(users) - {service_account})
    wanted = sorted(users)[:25] + ["svc-deleted"]

    result = await get_users_by_ids(wanted, _deps(admin))

    assert admin.page_queries, "26 misses in a 39-user realm must use the scan"
    assert sorted(admin.get_user_calls) == [service_account, "svc-deleted"]
    assert result[service_account].username == users[service_account]["username"]
    assert result["svc-deleted"].id == "svc-deleted"
    assert result["svc-deleted"].username is None


@pytest.mark.asyncio
async def test_many_misses_in_a_large_directory_stay_per_id_and_bounded() -> None:
    users = _users("big", 30)
    admin = _FakeKeycloakAdmin(users, total_users=users_service._USER_PAGE_SIZE * 100)

    result = await get_users_by_ids(sorted(users), _deps(admin))

    assert admin.page_queries == []
    assert sorted(admin.get_user_calls) == sorted(users)
    assert admin.max_in_flight <= users_service._PER_ID_LOOKUP_CONCURRENCY
    assert len(result) == 30


@pytest.mark.asyncio
async def test_scan_is_skipped_when_its_sequential_pages_outlast_parallel_lookups() -> (
    None
):
    """25 misses take 3 rounds of parallel lookups; a 1000-user realm takes 5
    sequential pages. Fewer calls, but slower: stay per-id."""
    users = _users("rounds", 25)
    admin = _FakeKeycloakAdmin(users, total_users=1000)

    await get_users_by_ids(sorted(users), _deps(admin))

    assert admin.count_calls == 1
    assert admin.page_queries == []
    assert sorted(admin.get_user_calls) == sorted(users)


@pytest.mark.asyncio
async def test_few_misses_skip_the_directory_count() -> None:
    users = _users("small", 3)
    admin = _FakeKeycloakAdmin(users)

    await get_users_by_ids(sorted(users), _deps(admin))

    assert admin.count_calls == 0
    assert admin.page_queries == []
    assert sorted(admin.get_user_calls) == sorted(users)
