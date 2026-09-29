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

"""Account status, checked once per authenticated request.

The real shared dependency and exception handler serve a FastAPI app; the
relationship engine is the real OpenFGA engine over a store holding suspensions
only, installed the way each service installs it at startup.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from fred_core.common import get_config
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.logs.audit_log import AUDIT_LOGGER_NAME
from fred_core.security import delegation, oidc
from fred_core.security.delegation import DelegationConfig, enforce_account_status
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacReference,
    TeamPermission,
)
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser
from fred_core.tests.security.rebac_fakes import (
    AccountStatusStore,
    account_status_engine,
)
from fred_core.users.store.postgres_user_store import get_user_store

_ISSUER = "https://identity.invalid/realms/test"
_PERSON = "person-canary"
_GRANTED = "granted-person-canary"
_SERVICE = "service-canary"
_WORKLOAD = "workload-canary"
_GRANT = {"person": _GRANTED, "run": "run-canary", "agent": "agent-canary"}
_CANARIES = (_PERSON, _GRANTED, _SERVICE, _WORKLOAD, *_GRANT.values(), "upstream")
_TEAM = RebacReference(Resource.TEAM, "team-canary")
_ACCEPT = DelegationConfig(accept_delegated_calls=True)
_ACT = DelegationConfig(act_for_people=True)
_HIGHER = RebacEngine.HIGHER_CONSISTENCY

_BEARERS = {
    "person": KeycloakUser(uid=_PERSON, username="p", roles=[], client_id="app"),
    "service": KeycloakUser(
        uid=_SERVICE, username="s", roles=[SERVICE_AGENT_ROLE], client_id="kb-pod"
    ),
    "workload": KeycloakUser(
        uid=_WORKLOAD,
        username="w",
        roles=[SERVICE_AGENT_ROLE],
        client_id="agent-runtime",
        token_issuer=_ISSUER,
        token_audiences=frozenset({"fred-delegation"}),
        token_type="Bearer",  # nosec B106 - protocol metadata
        caller_roles=frozenset({"delegation_caller"}),
    ),
}
# (bearer presented, grant beside it, subject the request names)
_SUBJECTS = {
    "signed-in-person": ("person", None, _PERSON),
    "person-named-by-a-grant": ("workload", _GRANT, _GRANTED),
    "service-identity": ("service", None, _SERVICE),
}
_CASES = [
    pytest.param(_ACCEPT, *_SUBJECTS[kind], id=f"accept_delegated_calls-{kind}")
    for kind in _SUBJECTS
] + [
    pytest.param(_ACT, *_SUBJECTS[kind], id=f"act_for_people-{kind}")
    for kind in ("signed-in-person", "service-identity")
]


@pytest.fixture(autouse=True)
def _restore_delegation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: _BEARERS[token])
    with delegation.preserved_delegation():
        yield


def _switch_on(config: DelegationConfig, store: AccountStatusStore | None) -> None:
    """Start the way a service does: the block, then the engine for the check."""
    delegation.initialize_delegation(config, issuers=[_ISSUER], user_clients=["app"])
    if store is not None:
        asyncio.run(enforce_account_status(account_status_engine(store)))


def _client(store: AccountStatusStore, served: list[str]) -> TestClient:
    """One route making three engine decisions about its subject."""
    app = FastAPI()
    register_exception_handlers(app)
    engine = account_status_engine(store)

    @app.get("/decide")
    async def decide(user=Depends(oidc.get_current_user)) -> dict[str, Any]:
        served.append(user.uid)
        subject = RebacReference(Resource.USER, user.uid)
        await engine.has_permission(subject, TeamPermission.CAN_READ, _TEAM)
        await engine.has_permissions(
            subject, [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO], _TEAM
        )
        await engine.lookup_resources(subject, TeamPermission.CAN_READ, Resource.TEAM)
        return {"subject": user.uid}

    app.dependency_overrides[get_config] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version=None)
    )
    app.dependency_overrides[get_user_store] = lambda: None
    return TestClient(app)


def _get(client: TestClient, bearer: str, grant: dict[str, str] | None):
    return client.get(
        "/decide", params=grant, headers={"Authorization": f"Bearer {bearer}"}
    )


@contextmanager
def _every_record() -> Iterator[list[logging.LogRecord]]:
    """Each service-side record at any level, with the test's own handler."""
    records: dict[int, logging.LogRecord] = {}

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # The test client logs the URL it requested; the service's lines count.
            if not record.name.startswith(("httpx", "httpcore")):
                records[id(record)] = record

    handler = _Capture(level=logging.DEBUG)
    loggers = [logging.getLogger(), logging.getLogger(AUDIT_LOGGER_NAME)]
    levels = [logger.level for logger in loggers]
    captured: list[logging.LogRecord] = []
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    try:
        yield captured
    finally:
        for logger, level in zip(loggers, levels):
            logger.removeHandler(handler)
            logger.setLevel(level)
        captured.extend(records.values())


def _rendered(records: list[logging.LogRecord]) -> str:
    return repr([{**vars(record), "text": record.getMessage()} for record in records])


def _account_refusals(records: list[logging.LogRecord]) -> list[tuple[str, str]]:
    return [
        (vars(r)["outcome"], vars(r)["reason"])
        for r in records
        if getattr(r, "audit_event", None) == "authorization.account.refused"
    ]


@pytest.mark.parametrize(("config", "bearer", "grant", "subject"), _CASES)
def test_each_request_checks_its_subject_once(
    config: DelegationConfig, bearer: str, grant: dict[str, str] | None, subject: str
) -> None:
    store, served = AccountStatusStore(), []
    _switch_on(config, store)

    response = _get(_client(store, served), bearer, grant)

    assert response.status_code == 200
    assert served == [subject]
    assert store.account_status_checks() == [(f"user:{subject}", _HIGHER)]
    # The route's own check, batch check and lookup keep the caller's consistency.
    assert [check[3] for check in store.checks] == [_HIGHER, None]
    assert [consistency for _, consistency in store.batch_checks] == [None]
    assert [call[3] for call in store.list_objects_calls] == [None]


@pytest.mark.parametrize(("config", "bearer", "grant", "subject"), _CASES)
def test_a_suspended_subject_is_refused_before_the_route(
    config: DelegationConfig, bearer: str, grant: dict[str, str] | None, subject: str
) -> None:
    store, served = AccountStatusStore(suspended={subject}), []
    _switch_on(config, store)

    with _every_record() as records:
        response = _get(_client(store, served), bearer, grant)

    assert response.status_code == 403
    assert response.headers["X-Fred-Denial-Cause"] == "account_suspended"
    assert served == []
    assert store.account_status_checks() == [(f"user:{subject}", _HIGHER)]
    assert store.batch_checks == store.list_objects_calls == []
    assert _account_refusals(records) == [("refused", "account_suspended")]
    for canary in _CANARIES:
        assert canary not in _rendered(records)
        assert canary not in response.text


@pytest.mark.parametrize(("config", "bearer", "grant", "subject"), _CASES)
def test_an_unavailable_account_status_check_is_503(
    config: DelegationConfig, bearer: str, grant: dict[str, str] | None, subject: str
) -> None:
    store, served = AccountStatusStore(unavailable=True), []
    _switch_on(config, store)

    with _every_record() as records:
        response = _get(_client(store, served), bearer, grant)

    assert response.status_code == 503
    assert response.headers["X-Fred-Denial-Cause"] == "account_status_unavailable"
    assert served == []
    assert len(store.account_status_checks()) == 1
    assert _account_refusals(records) == [("refused", "account_status_unavailable")]
    for canary in _CANARIES:
        assert canary not in _rendered(records)
        assert canary not in response.text


@pytest.mark.parametrize(("config", "bearer", "grant", "subject"), _CASES)
def test_a_switch_on_without_an_installed_engine_refuses_every_request(
    config: DelegationConfig, bearer: str, grant: dict[str, str] | None, subject: str
) -> None:
    store, served = AccountStatusStore(), []
    _switch_on(config, None)

    response = _get(_client(store, served), bearer, grant)

    assert response.status_code == 503
    assert response.headers["X-Fred-Denial-Cause"] == "account_status_unavailable"
    assert served == []
    assert store.checks == []


@pytest.mark.parametrize("config", [_ACCEPT, _ACT])
def test_a_switch_on_refuses_an_engine_that_does_not_enforce_account_status(
    config: DelegationConfig,
) -> None:
    store, served = AccountStatusStore(suspended={_PERSON}), []
    engine = account_status_engine(store, requires_active_accounts=False)
    _switch_on(config, None)

    with pytest.raises(ValueError):
        asyncio.run(enforce_account_status(engine))
    response = _get(_client(store, served), "person", None)

    assert response.status_code == 503
    assert served == []
    assert store.checks == []


@pytest.mark.parametrize("bearer", ["person", "service", "workload"])
def test_both_switches_off_make_no_account_status_check(bearer: str) -> None:
    store, served = AccountStatusStore(suspended={_PERSON, _SERVICE, _WORKLOAD}), []
    _switch_on(DelegationConfig(), store)

    response = _get(_client(store, served), bearer, _GRANT)

    assert response.status_code == 200
    assert served == [_BEARERS[bearer].uid]
    assert store.account_status_checks() == []
