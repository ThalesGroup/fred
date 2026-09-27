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
from typing import cast
from unittest.mock import AsyncMock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser
from fred_core.users.store import BaseUserStore

_GCU_VERSION = "2026-01"


def _user_store(accepted: str | None = None) -> BaseUserStore:
    store = create_autospec(BaseUserStore, instance=True, spec_set=True)
    store.find_user_by_id.return_value = (
        SimpleNamespace(gcuVersionAccepted=SimpleNamespace(value=accepted))
        if accepted is not None
        else None
    )
    return store


@pytest.fixture(autouse=True)
def _gcu_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)


@pytest.fixture
def configuration() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(gcu_version=_GCU_VERSION))


@pytest.fixture
def bearer_token() -> str:
    return uuid4().hex


def _request() -> Request:
    """A bare request: the gate reads nothing from it, and delegation is off."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        }
    )


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
async def test_a_service_passes_without_a_user_record(
    monkeypatch, configuration, bearer_token
):
    service, store = _service(), _user_store()
    _bearer_resolves_to(monkeypatch, service)

    admitted = await oidc.get_current_user_or_service(
        request=_request(),
        token=bearer_token,
        user_store=store,
        configuration=configuration,
    )

    assert admitted is service
    cast(AsyncMock, store.find_user_by_id).assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_user_still_refuses_a_service(
    monkeypatch, configuration, bearer_token
):
    service, store = _service(), _user_store()
    _bearer_resolves_to(monkeypatch, service)

    with pytest.raises(HTTPException) as exc:
        await oidc.get_current_user(
            request=_request(),
            token=bearer_token,
            user_store=store,
            configuration=configuration,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "user_not_accept_gcu"


@pytest.mark.parametrize(
    "dependency", [oidc.get_current_user, oidc.get_current_user_or_service]
)
@pytest.mark.asyncio
async def test_a_human_without_accepted_gcu_is_refused(
    monkeypatch, configuration, dependency, bearer_token
):
    human, store = _human(), _user_store()
    _bearer_resolves_to(monkeypatch, human)

    with pytest.raises(HTTPException) as exc:
        await dependency(
            request=_request(),
            token=bearer_token,
            user_store=store,
            configuration=configuration,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "user_not_accept_gcu"
    cast(AsyncMock, store.find_user_by_id).assert_awaited_once_with(UUID(human.uid))


@pytest.mark.parametrize(
    "dependency", [oidc.get_current_user, oidc.get_current_user_or_service]
)
@pytest.mark.asyncio
async def test_a_human_with_accepted_gcu_passes(
    monkeypatch, configuration, dependency, bearer_token
):
    human, store = _human(), _user_store(accepted=_GCU_VERSION)
    _bearer_resolves_to(monkeypatch, human)

    admitted = await dependency(
        request=_request(),
        token=bearer_token,
        user_store=store,
        configuration=configuration,
    )

    assert admitted is human
    cast(AsyncMock, store.find_user_by_id).assert_awaited_once_with(UUID(human.uid))


@pytest.mark.parametrize(
    "dependency", [oidc.get_current_user, oidc.get_current_user_or_service]
)
@pytest.mark.asyncio
async def test_an_asserted_person_is_admitted_without_a_record(
    monkeypatch, configuration, dependency, bearer_token
):
    """A person a workload speaks for accepted the terms with their own token.

    Their acceptance was checked when the run was admitted, and the workload
    carries no acceptance row of its own, so neither gate may look one up.
    """
    asserted = AssertedUser(
        uid=str(uuid4()), client_id="agentic", run_id="run-1", agent_id="agent-1"
    )
    store = _user_store()

    async def _asserted(request, token):
        return asserted

    monkeypatch.setattr(oidc, "get_current_user_without_gcu", _asserted)

    admitted = await dependency(
        request=_request(),
        token=bearer_token,
        user_store=store,
        configuration=configuration,
    )

    assert admitted is asserted
    cast(AsyncMock, store.find_user_by_id).assert_not_awaited()
