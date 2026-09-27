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

"""Acceptance of a delegation grant in the shared user dependency.

Bearer first, then the parameters, then the principal: these tests drive the
real dependency through a FastAPI app and assert what the request ends up with
as its subject, what is audited, and that an endpoint's own body still parses.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import Depends, FastAPI, Request, Security
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fred_core.common import get_config
from fred_core.logs.audit_log import AUDIT_LOGGER_NAME
from fred_core.security import delegation, oidc
from fred_core.security.delegation import (
    AUDIT_GRANT_ACCEPTED,
    AUDIT_GRANT_REJECTED,
    DelegationConfig,
)
from fred_core.security.structure import (
    SERVICE_AGENT_ROLE,
    KeycloakUser,
    PrincipalContext,
    is_service_agent,
)
from fred_core.security.whitelist_access_control import access_control as whitelist
from fred_core.users.store.postgres_user_store import get_user_store

_CALLER = "agent-backend"
_OTHER_CALLER = "some-other-client"
_BEARER = "opaque-test-value"  # stands in for a token; never a real credential
_GRANT = {"person": "p-1", "run": "r-1", "agent": "a-1"}
_HEADERS = {"Authorization": f"Bearer {_BEARER}"}
_ISSUER = "https://identity.invalid/realms/test"
_AUDIENCE = "fred-delegation"
_LOGIN_CLIENT = "app"


class _Payload(BaseModel):
    question: str


class _AuditSink(logging.Handler):
    """Own handler on the audit logger: caplog goes deaf once log_setup() ran."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def caller() -> KeycloakUser:
    return KeycloakUser(
        uid="svc-1",
        username="svc",
        roles=[SERVICE_AGENT_ROLE],
        client_id=_CALLER,
        token_issuer=_ISSUER,
        token_audiences=frozenset({_AUDIENCE}),
        token_type="Bearer",  # nosec B106 - protocol metadata or synthetic fixture
        caller_roles=frozenset({"delegation_caller"}),
    )


@pytest.fixture(autouse=True)
def _verified_bearer(monkeypatch: pytest.MonkeyPatch, caller: KeycloakUser) -> None:
    # decode_jwt's contract is "a KeycloakUser, or HTTPException": signature and
    # expiry are covered by test_oidc_strict.py / test_oidc_token_lifetime.py.
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: caller)


@pytest.fixture(autouse=True)
def _restore_delegation() -> Iterator[None]:
    with delegation.preserved_delegation():
        yield


@pytest.fixture
def body_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every real body read; not doing one is the point of the caller gate."""
    seen: list[str] = []
    read_json_object = delegation._read_json_object

    async def counting(request: Request) -> Any:
        seen.append(request.url.path)
        return await read_json_object(request)

    monkeypatch.setattr(delegation, "_read_json_object", counting)
    return seen


@pytest.fixture
def audit() -> Iterator[_AuditSink]:
    sink = _AuditSink()
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    previous_level = audit_logger.level
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(sink)
    yield sink
    audit_logger.removeHandler(sink)
    audit_logger.setLevel(previous_level)


def _accept_delegated_calls() -> None:
    delegation.initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=[_ISSUER],
        user_clients=[_LOGIN_CLIENT],
    )


def _without_the_role(monkeypatch: pytest.MonkeyPatch, caller: KeycloakUser) -> None:
    untrusted = caller.model_copy(update={"caller_roles": frozenset()})
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: untrusted)


def _describe(user: Any) -> dict[str, Any]:
    return {
        "kind": type(user).__name__,
        "uid": user.uid,
        "client_id": user.client_id,
        "run_id": getattr(user, "run_id", None),
        "agent_id": getattr(user, "agent_id", None),
        "roles": user.roles,
    }


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get("/who", operation_id="who")
    async def who(user=Depends(oidc.get_current_user)) -> dict[str, Any]:
        return _describe(user)

    @app.get("/without-operation-id")
    async def without_operation_id(
        user=Depends(oidc.get_current_user),
    ) -> dict[str, Any]:
        return _describe(user)

    @app.post("/ask", operation_id="ask")
    async def ask(
        payload: _Payload, user=Depends(oidc.get_current_user)
    ) -> dict[str, Any]:
        return {**_describe(user), "question": payload.question}

    @app.post("/ping", operation_id="ping")
    async def ping(user=Depends(oidc.get_current_user)) -> dict[str, Any]:
        return _describe(user)

    @app.post("/manual", operation_id="manual")
    async def manual(
        request: Request, user=Depends(oidc.get_current_user)
    ) -> dict[str, Any]:
        # No declared body: the dependency reads it first, so the handler's own
        # read must still see it.
        return {**_describe(user), "body": await request.json()}

    @app.get("/own", operation_id="own")
    async def own(user=Depends(oidc.require_own_credential)) -> dict[str, Any]:
        return _describe(user)

    @app.get("/context", operation_id="context")
    async def context(
        principals: PrincipalContext = Depends(oidc.get_principal_context),
    ) -> dict[str, str | bool]:
        return {
            "caller": principals.caller.uid,
            "subject": principals.subject.uid,
            "caller_is_service": is_service_agent(principals.caller),
            "subject_is_service": is_service_agent(principals.subject),
        }

    @app.post("/mcp", operation_id="mcp_http")
    async def mcp(
        request: Request, token: str = Security(oidc.oauth2_scheme)
    ) -> dict[str, Any]:
        user = await oidc.resolve_request_principal(
            request, oidc.decode_jwt(token), query_only=True
        )
        return {**_describe(user), "body": (await request.body()).decode()}

    app.dependency_overrides[get_config] = lambda: SimpleNamespace(
        app=SimpleNamespace(gcu_version=None)
    )
    app.dependency_overrides[get_user_store] = lambda: None
    return TestClient(app)


# ---------------------------------------------------------------------------
# Accepted
# ---------------------------------------------------------------------------


def test_query_grant_from_a_trusted_caller_names_the_person(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.get("/who", params=_GRANT, headers=_HEADERS).json()

    assert body == {
        "kind": "AssertedUser",
        "uid": "p-1",
        "client_id": _CALLER,
        "run_id": "r-1",
        "agent_id": "a-1",
        "roles": [],
    }
    audited = _one(audit)
    assert audited["audit_event"] == AUDIT_GRANT_ACCEPTED
    assert audited["outcome"] == "accepted"
    assert audited["reason"] == "grant_validated"
    for canary in (_CALLER, _BEARER, *_GRANT.values()):
        assert canary not in str(audited)


def test_request_context_retains_the_caller_and_subject(client: TestClient) -> None:
    _accept_delegated_calls()

    body = client.get("/context", params=_GRANT, headers=_HEADERS).json()

    assert body == {
        "caller": "svc-1",
        "subject": "p-1",
        "caller_is_service": True,
        "subject_is_service": False,
    }


def test_endpoint_without_operation_metadata_accepts_the_trusted_identity(
    client: TestClient,
) -> None:
    _accept_delegated_calls()

    response = client.get("/without-operation-id", params=_GRANT, headers=_HEADERS)

    assert response.status_code == 200
    assert response.json()["kind"] == "AssertedUser"
    assert response.json()["uid"] == "p-1"


@pytest.mark.parametrize(
    "updates",
    [
        {"client_id": _LOGIN_CLIENT},
        {"token_type": "ID"},  # nosec B105 - protocol metadata or synthetic fixture
        {"token_issuer": "https://other.invalid/realms/test"},  # nosec B105 - protocol metadata or synthetic fixture
        {"token_audiences": frozenset({"other-receiver"})},
    ],
)
def test_a_login_client_token_or_invalid_token_context_cannot_delegate(
    client: TestClient,
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
) -> None:
    _accept_delegated_calls()
    monkeypatch.setattr(
        oidc, "decode_jwt", lambda token: caller.model_copy(update=updates)
    )

    response = client.get("/who", params=_GRANT, headers=_HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"] == "delegation_not_allowed"


def test_query_only_grant_resolution_does_not_read_the_mcp_body(
    client: TestClient, body_reads: list[str]
) -> None:
    _accept_delegated_calls()

    response = client.post(
        "/mcp",
        content=b'{"jsonrpc":"2.0"}',
        headers={**_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "KeycloakUser"
    assert response.json()["body"] == '{"jsonrpc":"2.0"}'
    assert body_reads == []


def test_query_only_grant_resolution_accepts_query_metadata_without_reading_body(
    client: TestClient, body_reads: list[str]
) -> None:
    _accept_delegated_calls()

    response = client.post(
        "/mcp",
        params=_GRANT,
        content=b'{"jsonrpc":"2.0"}',
        headers={**_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "AssertedUser"
    assert response.json()["uid"] == "p-1"
    assert response.json()["body"] == '{"jsonrpc":"2.0"}'
    assert body_reads == []


def test_asserted_subject_requires_a_uid_whitelist_entry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    whitelist_file = tmp_path / "users.txt"
    monkeypatch.setattr(whitelist, "_WHITELIST_PATH", whitelist_file)
    monkeypatch.setattr(whitelist, "_WHITELIST_CACHE_KEY", str(whitelist_file))
    whitelist._WHITELIST_CACHE.clear()
    _accept_delegated_calls()
    whitelist_file.write_text("person@example.com\n", encoding="utf-8")

    authenticated_denied = client.get("/who", headers=_HEADERS)
    denied = client.get("/who", params=_GRANT, headers=_HEADERS)
    whitelist_file.write_text("uid:p-1\n", encoding="utf-8")
    whitelist._WHITELIST_CACHE.clear()
    allowed = client.get("/who", params=_GRANT, headers=_HEADERS)

    assert authenticated_denied.status_code == 403
    assert denied.status_code == 403
    assert denied.json()["detail"] == "user_not_whitelisted"
    assert allowed.status_code == 200
    assert allowed.json()["uid"] == "p-1"


def test_body_grant_names_the_person_and_the_endpoint_still_parses_its_body(
    client: TestClient,
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask", json={"question": "how many?", **_GRANT}, headers=_HEADERS
    ).json()

    assert body["kind"] == "AssertedUser"
    assert body["uid"] == "p-1"
    assert body["question"] == "how many?"


def test_a_handler_reading_the_body_itself_still_sees_it(client: TestClient) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/manual", json={"question": "how many?", **_GRANT}, headers=_HEADERS
    ).json()

    assert body["kind"] == "AssertedUser"
    assert body["body"]["question"] == "how many?"


# ---------------------------------------------------------------------------
# No subject
# ---------------------------------------------------------------------------


def test_grant_from_a_caller_without_the_role_is_refused_and_audited(
    client: TestClient,
    audit: _AuditSink,
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ignored, the grant would leave a service identity acting as itself for a run.
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller)

    response = client.get("/who", params=_GRANT, headers=_HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"] == "delegation_not_allowed"
    audited = _one(audit)
    assert audited["audit_event"] == AUDIT_GRANT_REJECTED
    assert audited["outcome"] == "rejected"
    assert audited["reason"] == "caller_not_trusted"
    for canary in (_CALLER, _BEARER, *_GRANT.values()):
        assert canary not in str(audited)


def test_a_trusted_caller_without_parameters_acts_for_nobody(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.get("/who", headers=_HEADERS).json()

    assert body["kind"] == "KeycloakUser"
    assert body["uid"] == "svc-1"
    assert audit.records == []


@pytest.mark.parametrize(
    "params",
    [
        {"person": "p-1", "run": "r-1"},
        {"person": "p-1"},
        {"person": "  ", "run": "r-1", "agent": "a-1"},
    ],
)
def test_partial_or_blank_parameters_name_nobody(
    client: TestClient, audit: _AuditSink, params: dict[str, str]
) -> None:
    _accept_delegated_calls()

    body = client.get("/who", params=params, headers=_HEADERS).json()

    assert body["kind"] == "KeycloakUser"
    assert _one(audit)["reason"] == "invalid_parameters"


def test_a_non_string_parameter_in_the_body_names_nobody(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask",
        json={"question": "q", "person": {"uid": "p-1"}, "run": "r-1", "agent": "a-1"},
        headers=_HEADERS,
    ).json()

    assert body["kind"] == "KeycloakUser"
    assert _one(audit)["reason"] == "invalid_parameters"


def test_a_person_without_the_role_never_has_its_body_read(
    client: TestClient,
    audit: _AuditSink,
    body_reads: list[str],
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller.model_copy(update={"roles": []}))

    response = client.post(
        "/ask",
        json={"question": "q", **_GRANT},
        headers=_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "KeycloakUser"
    assert body_reads == []
    assert audit.records == []


def test_a_body_grant_from_a_service_identity_without_the_role_is_refused(
    client: TestClient,
    audit: _AuditSink,
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A workload provisioned without the role must not pass as the service
    # identity it also is, whichever transport its grant rides.
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller)

    response = client.post("/ask", json={"question": "q", **_GRANT}, headers=_HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"] == "delegation_not_allowed"
    assert _one(audit)["reason"] == "caller_not_trusted"


def test_a_tool_mount_never_reads_the_body_of_a_service_identity_without_the_role(
    client: TestClient,
    audit: _AuditSink,
    body_reads: list[str],
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A mount's body is the tool call, left whole for the protocol it carries.
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller)

    response = client.post(
        "/mcp",
        content=b'{"jsonrpc":"2.0"}',
        headers={**_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "KeycloakUser"
    assert response.json()["body"] == '{"jsonrpc":"2.0"}'
    assert body_reads == []
    assert audit.records == []


def test_a_service_identity_without_the_role_and_without_a_grant_is_itself(
    client: TestClient,
    audit: _AuditSink,
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller)

    response = client.post(
        "/ping",
        content=b"{not json at all",
        headers={**_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "KeycloakUser"
    assert response.json()["roles"] == [SERVICE_AGENT_ROLE]
    assert audit.records == []


def test_a_trusted_caller_has_its_body_read_for_a_grant(
    client: TestClient, body_reads: list[str]
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask", json={"question": "q", **_GRANT}, headers=_HEADERS
    ).json()

    assert body["kind"] == "AssertedUser"
    assert body_reads == ["/ask"]


def test_a_partial_query_set_from_a_caller_without_the_role_is_not_audited(
    client: TestClient,
    audit: _AuditSink,
    caller: KeycloakUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_delegated_calls()
    _without_the_role(monkeypatch, caller)

    body = client.get(
        "/who", params={"person": "p-1", "run": "r-1"}, headers=_HEADERS
    ).json()

    assert body["kind"] == "KeycloakUser"
    assert audit.records == []  # ordinary traffic, not an attempt


def test_a_partial_body_set_from_a_trusted_caller_is_audited(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask", json={"question": "q", "person": "p-1", "run": "r-1"}, headers=_HEADERS
    ).json()

    assert body["kind"] == "KeycloakUser"
    assert _one(audit)["reason"] == "invalid_parameters"


def test_an_unusable_body_from_a_trusted_caller_leaves_the_request_alone(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    response = client.post(
        "/ping",
        content=b"{not json at all",
        headers={**_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "KeycloakUser"
    assert audit.records == []


def test_parameters_inside_tool_arguments_are_not_a_grant(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask",
        json={"question": "q", "arguments": _GRANT},
        headers=_HEADERS,
    ).json()

    assert body["kind"] == "KeycloakUser"
    assert body["uid"] == "svc-1"
    assert audit.records == []  # nothing that looks like a grant was presented


def test_parameters_split_across_query_and_body_are_not_a_grant(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.post(
        "/ask",
        params={"person": "p-1"},
        json={"question": "q", "run": "r-1", "agent": "a-1"},
        headers=_HEADERS,
    ).json()

    assert body["kind"] == "KeycloakUser"
    assert _one(audit)["reason"] == "invalid_parameters"


def test_form_encoded_parameters_are_not_a_grant(
    client: TestClient, audit: _AuditSink
) -> None:
    _accept_delegated_calls()

    body = client.post("/ping", data=_GRANT, headers=_HEADERS).json()

    assert body["kind"] == "KeycloakUser"
    assert audit.records == []


# ---------------------------------------------------------------------------
# Delegated calls not accepted, authentication off, and the own-credential guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [DelegationConfig(), DelegationConfig(act_for_people=True)],
    ids=["delegation_off", "act_for_people_only"],
)
def test_without_accepting_delegated_calls_the_dependency_behaves_as_before(
    client: TestClient, audit: _AuditSink, config: DelegationConfig
) -> None:
    # Same trusted caller and whole grant as the accepted case: only the switch differs.
    delegation.initialize_delegation(
        config, issuers=[_ISSUER], user_clients=[_LOGIN_CLIENT]
    )

    body = client.get("/who", params=_GRANT, headers=_HEADERS).json()

    assert body["kind"] == "KeycloakUser"
    assert body["uid"] == "svc-1"
    assert audit.records == []


def test_with_authentication_disabled_no_grant_is_read(
    client: TestClient, audit: _AuditSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    _accept_delegated_calls()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", False)

    body = client.get("/who", params=_GRANT, headers=_HEADERS).json()

    assert body["kind"] == "KeycloakUser"
    assert body["uid"] == "admin"
    assert audit.records == []


def test_an_operation_requiring_its_own_credential_refuses_an_asserted_person(
    client: TestClient,
) -> None:
    _accept_delegated_calls()

    refused = client.get("/own", params=_GRANT, headers=_HEADERS)
    accepted = client.get("/own", headers=_HEADERS)

    assert refused.status_code == 403
    assert refused.json()["detail"] == "requires_own_credential"
    assert accepted.status_code == 200
    assert accepted.json()["uid"] == "svc-1"


def _one(audit: _AuditSink) -> dict[str, Any]:
    """The single audit line emitted, as the fields a log pipeline would see."""
    assert len(audit.records) == 1
    record = audit.records[0]
    emitted = {**record.__dict__, "message": record.getMessage()}
    for canary in (_CALLER, _OTHER_CALLER, _BEARER, *_GRANT.values()):
        assert canary not in str(emitted)
    return emitted
