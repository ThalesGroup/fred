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

"""Who the GCU gate admits.

`get_current_user` refuses any subject without a persisted acceptance of the
configured GCU version. A service identity has no record to accept with, so
`get_current_user_or_service` lets a workload through and holds every human to
exactly the same gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from fred_core.security import oidc
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser

_GCU_VERSION = "2026-01"


class _RecordingUserStore:
    """Records who was looked up; answers with the acceptance it was given."""

    def __init__(self, accepted: str | None = None) -> None:
        self._accepted = accepted
        self.looked_up: list[UUID] = []

    async def find_user_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.looked_up.append(user_id)
        if self._accepted is None:
            return None
        return SimpleNamespace(gcuVersionAccepted=SimpleNamespace(value=self._accepted))


@pytest.fixture(autouse=True)
def _gcu_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)


@pytest.fixture
def configuration() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(gcu_version=_GCU_VERSION))


def _bearer_resolves_to(monkeypatch: pytest.MonkeyPatch, user: KeycloakUser) -> None:
    """Make the token resolve to `user` without a signature to verify."""
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: user)


def _service() -> KeycloakUser:
    return KeycloakUser(
        uid=str(uuid4()),
        username="kb-pod",
        roles=[SERVICE_AGENT_ROLE],
        client_id="kb-pod",
    )


def _human() -> KeycloakUser:
    return KeycloakUser(uid=str(uuid4()), username="alice", roles=[])


@pytest.mark.asyncio
async def test_a_service_passes_without_a_user_record(monkeypatch, configuration):
    service, store = _service(), _RecordingUserStore()
    _bearer_resolves_to(monkeypatch, service)

    admitted = await oidc.get_current_user_or_service(
        token="t", user_store=store, configuration=configuration
    )

    assert admitted is service
    assert store.looked_up == []


@pytest.mark.asyncio
async def test_get_current_user_still_refuses_a_service(monkeypatch, configuration):
    service, store = _service(), _RecordingUserStore()
    _bearer_resolves_to(monkeypatch, service)

    with pytest.raises(HTTPException) as exc:
        await oidc.get_current_user(
            token="t", user_store=store, configuration=configuration
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "user_not_accept_gcu"


@pytest.mark.parametrize(
    "dependency", [oidc.get_current_user, oidc.get_current_user_or_service]
)
@pytest.mark.asyncio
async def test_a_human_without_accepted_gcu_is_refused(
    monkeypatch, configuration, dependency
):
    human, store = _human(), _RecordingUserStore()
    _bearer_resolves_to(monkeypatch, human)

    with pytest.raises(HTTPException) as exc:
        await dependency(token="t", user_store=store, configuration=configuration)

    assert exc.value.status_code == 403
    assert exc.value.detail == "user_not_accept_gcu"
    assert store.looked_up == [UUID(human.uid)]


@pytest.mark.parametrize(
    "dependency", [oidc.get_current_user, oidc.get_current_user_or_service]
)
@pytest.mark.asyncio
async def test_a_human_with_accepted_gcu_passes(monkeypatch, configuration, dependency):
    human, store = _human(), _RecordingUserStore(accepted=_GCU_VERSION)
    _bearer_resolves_to(monkeypatch, human)

    admitted = await dependency(
        token="t", user_store=store, configuration=configuration
    )

    assert admitted is human
    assert store.looked_up == [UUID(human.uid)]
