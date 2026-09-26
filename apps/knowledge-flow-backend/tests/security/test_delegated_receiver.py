from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi_mcp import AuthConfig, FastApiMCP
from fred_core import StandingAuthorizationError
from fred_core.security import oidc
from fred_core.security.delegation import DelegationConfig, initialize_delegation
from fred_core.security.mcp_delegation import (
    declare_delegation_parameters,
    mcp_mount_auth,
    strip_grant_tool_fields,
)
from fred_core.security.mcp_delegation_fastapi import DelegatedFastApiMCP
from fred_core.security.oidc import get_current_user_without_gcu
from fred_core.security.structure import KeycloakUser

from knowledge_flow_backend.compat import fastapi_mcp_patch  # noqa: F401
from knowledge_flow_backend.features.content.content_service import ContentService
from knowledge_flow_backend.features.metadata.service import MetadataService

_HEADERS = {
    "authorization": "Bearer synthetic-workload-token",
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
_GRANT = {"person": "person-a", "run": "run-a", "agent": "agent-a"}
_NOW = 2_000_000_000
_REAL_DECODE_JWT = oidc.decode_jwt


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime.fromtimestamp(_NOW, timezone.utc)
        return value if tz is not None else value.replace(tzinfo=None)


class _SigningKey:
    def __init__(self, key) -> None:
        self.key = key


class _Jwks:
    def __init__(self, key) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(self._key)


@pytest.fixture(autouse=True)
def _delegation_globals(monkeypatch) -> Iterator[None]:
    caller = KeycloakUser(
        uid="workload-subject",
        username="workload",
        roles=["service_agent"],
        email=None,
        client_id="agent-runtime",
        token_issuer="https://issuer.test/realms/fred",
        token_audiences=frozenset({"fred-delegation"}),
        token_type="Bearer",
        caller_roles=frozenset({"delegation_caller"}),
    )
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: caller)
    yield
    initialize_delegation(DelegationConfig())


def _configure() -> None:
    initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=["https://issuer.test/realms/fred"],
        user_clients=["app"],
    )


def _app_with_mcp() -> tuple[FastAPI, FastApiMCP]:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(declare_delegation_parameters)])

    @router.get("/documents", tags=["Documents"], operation_id="list_documents")
    async def list_documents(user=Depends(get_current_user_without_gcu)):
        return {"subject": user.uid, "roles": user.roles}

    app.include_router(router)
    mcp = strip_grant_tool_fields(
        DelegatedFastApiMCP(
            app,
            include_tags=["Documents"],
            auth_config=AuthConfig(dependencies=[Depends(mcp_mount_auth)]),
        )
    )
    mcp.mount_http(mount_path="/mcp")
    return app, mcp


def _mcp_call(
    client: TestClient,
    arguments: dict[str, str],
    *,
    grant: dict[str, str] | None = _GRANT,
    bearer: str = "synthetic-workload-token",
) -> dict:
    headers = {**_HEADERS, "authorization": f"Bearer {bearer}"}
    initialize = client.post(
        "/mcp",
        params=grant,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
    )
    assert initialize.status_code == 200
    assert "mcp-session-id" not in initialize.headers
    response = client.post(
        "/mcp",
        params=grant,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_documents", "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def signed_tokens(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://issuer.test/realms/fred"
    login_client = "app"
    monkeypatch.setattr(oidc, "decode_jwt", _REAL_DECODE_JWT)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", issuer)
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({issuer}))
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", login_client)
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", _Jwks(private_key.public_key()))
    monkeypatch.setattr(jwt.api_jwt, "datetime", _FixedDateTime)

    def token(*, subject: str, client: str, expires_at: int, caller: bool = True) -> str:
        # A delegating workload is addressed to the delegation audience and holds
        # its role; a person's token is addressed to the login client.
        claims: dict[str, object] = {"aud": login_client}
        if caller:
            claims = {
                "aud": "fred-delegation",
                "resource_access": {"fred-delegation": {"roles": ["delegation_caller"]}},
            }
        return jwt.encode(
            {
                "sub": subject,
                "azp": client,
                "iss": issuer,
                "typ": "Bearer",
                "iat": _NOW - 30,
                "exp": expires_at,
                **claims,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "synthetic"},
        )

    return token, issuer, login_client


def test_signed_receiver_keeps_rest_and_mcp_available_after_person_expiry(
    signed_tokens,
) -> None:
    token, issuer, login_client = signed_tokens
    initialize_delegation(DelegationConfig(accept_delegated_calls=True), issuers=[issuer], user_clients=[login_client])
    expired_person = token(subject="person-a", client="browser", expires_at=_NOW - 1, caller=False)
    workload = token(subject="workload-subject", client="agent-runtime", expires_at=_NOW + 300)
    expired_workload = token(subject="workload-subject", client="agent-runtime", expires_at=_NOW - 1)
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        person_response = client.get("/documents", headers={"Authorization": f"Bearer {expired_person}"})
        rest_response = client.get(
            "/documents",
            params=_GRANT,
            headers={"Authorization": f"Bearer {workload}"},
        )
        mcp_response = _mcp_call(
            client,
            {"person": "forged", "run": "forged", "agent": "forged"},
            bearer=workload,
        )
        expired_response = client.post(
            "/mcp",
            params=_GRANT,
            headers={**_HEADERS, "authorization": f"Bearer {expired_workload}"},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )

    assert person_response.status_code == 401
    assert rest_response.status_code == 200
    assert rest_response.json() == {"subject": "person-a", "roles": []}
    assert mcp_response["result"]["isError"] is False
    assert '"subject": "person-a"' in mcp_response["result"]["content"][0]["text"]
    assert "forged" not in mcp_response["result"]["content"][0]["text"]
    assert expired_response.status_code == 401


def test_rest_accepts_trusted_workload_delegation() -> None:
    _configure()
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        accepted = client.get("/documents", params=_GRANT, headers={"authorization": _HEADERS["authorization"]})

    assert accepted.status_code == 200
    assert accepted.json() == {"subject": "person-a", "roles": []}


def test_rest_route_metadata_is_optional_for_delegation() -> None:
    _configure()
    app = FastAPI()

    @app.get("/unnamed")
    async def unnamed(user=Depends(get_current_user_without_gcu)):
        return {"subject": user.uid, "roles": user.roles}

    route = next(route for route in app.routes if getattr(route, "path", None) == "/unnamed")
    assert getattr(route, "operation_id", None) is None

    with TestClient(app) as client:
        response = client.get("/unnamed", params=_GRANT, headers={"authorization": _HEADERS["authorization"]})

    assert response.status_code == 200
    assert response.json() == {"subject": "person-a", "roles": []}


def test_rest_refuses_a_grant_from_a_workload_without_the_role(monkeypatch) -> None:
    _configure()
    monkeypatch.setattr(
        oidc,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="untrusted-subject",
            username="untrusted",
            roles=["service_agent"],
            client_id="untrusted-client",
            token_issuer="https://issuer.test/realms/fred",
            token_audiences=frozenset({"knowledge-flow"}),
            token_type="Bearer",
        ),
    )
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        response = client.get(
            "/documents",
            params=_GRANT,
            headers={"authorization": _HEADERS["authorization"]},
        )

    # Served as itself, it would read under the service identity's shortcuts.
    assert response.status_code == 403
    assert response.json()["detail"] == "delegation_not_allowed"


def test_rest_delegation_preserves_endpoint_user_authorization() -> None:
    _configure()
    app = FastAPI()

    @app.get("/private")
    async def private(user=Depends(get_current_user_without_gcu)):
        if user.uid != "person-b":
            raise HTTPException(status_code=403, detail="forbidden")
        return {"subject": user.uid}

    with TestClient(app) as client:
        response = client.get(
            "/private",
            params=_GRANT,
            headers={"authorization": _HEADERS["authorization"]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_mcp_forwards_validated_outer_grant_and_strips_tool_forgery() -> None:
    _configure()
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        payload = _mcp_call(
            client,
            {"person": "forged", "run": "forged", "agent": "forged"},
        )

    assert payload["result"]["isError"] is False
    assert '"subject": "person-a"' in payload["result"]["content"][0]["text"]
    assert '"roles": []' in payload["result"]["content"][0]["text"]


def test_mcp_accepts_trusted_outer_grant() -> None:
    _configure()
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        payload = _mcp_call(client, {})

    assert payload["result"]["isError"] is False
    assert '"subject": "person-a"' in payload["result"]["content"][0]["text"]


def test_mcp_grant_context_does_not_leak_to_next_request() -> None:
    _configure()
    app, _ = _app_with_mcp()

    with TestClient(app) as client:
        delegated = _mcp_call(client, {})
        caller_only = _mcp_call(client, {}, grant=None)

    assert '"subject": "person-a"' in delegated["result"]["content"][0]["text"]
    assert '"subject": "workload-subject"' in caller_only["result"]["content"][0]["text"]


def test_mcp_tool_schema_does_not_offer_grant_fields() -> None:
    _configure()
    _, mcp = _app_with_mcp()

    schema = next(tool.inputSchema for tool in mcp.tools if tool.name == "list_documents")
    assert not set(_GRANT).intersection(schema.get("properties", {}))


@pytest.mark.asyncio
async def test_metadata_preserves_standing_denial() -> None:
    class _Rebac:
        async def lookup_user_resources(self, user, permission):
            raise StandingAuthorizationError()

    service = MetadataService.__new__(MetadataService)
    service.rebac = cast(Any, _Rebac())

    with pytest.raises(StandingAuthorizationError):
        await service.get_documents_metadata(KeycloakUser(uid="person-a", username="person", roles=[], email=None), {})


@pytest.mark.asyncio
async def test_content_does_not_fallback_after_standing_denial() -> None:
    service = ContentService.__new__(ContentService)

    async def _denied(user, document_uid):
        raise StandingAuthorizationError()

    service.get_document_metadata = _denied
    service._session_attachment_text = lambda user, document_uid: (_ for _ in ()).throw(AssertionError("standing denial reached attachment fallback"))

    with pytest.raises(StandingAuthorizationError):
        await service.get_markdown_preview(
            KeycloakUser(uid="person-a", username="person", roles=[], email=None),
            "document-a",
        )
