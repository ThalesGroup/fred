from __future__ import annotations

from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.delegation import DelegationConfig, initialize_delegation
from fred_core.security.oidc import get_current_user_without_gcu
from fred_runtime.common.mcp_interceptors import DelegatedAuthorityInterceptor
from fred_runtime.common.outbound_credentials import static_person_provider
from fred_runtime.runtime_support.authority import AuthorityLostError
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

_NOW = 2_000_000_000


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


@pytest.fixture
def signed_receiver(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://issuer.test/realms/fred"
    login_client = "app"
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", issuer)
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({issuer}))
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", login_client)
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", _Jwks(private_key.public_key()))
    monkeypatch.setattr(jwt.api_jwt, "datetime", _FixedDateTime)
    initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=[issuer],
        user_clients=[login_client],
    )

    def token(
        *,
        subject: str,
        client: str,
        expires_at: int,
        caller: bool = True,
    ) -> str:
        # A delegating workload is addressed to the delegation audience and holds
        # its role; anything else is addressed to the login client.
        claims: dict[str, object] = {"aud": login_client}
        if caller:
            claims = {
                "aud": "fred-delegation",
                "resource_access": {
                    "fred-delegation": {"roles": ["delegation_caller"]}
                },
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

    app = FastAPI()

    @app.get("/documents", operation_id="read_documents")
    async def documents(user=Depends(get_current_user_without_gcu)):
        return {"subject": user.uid, "roles": user.roles}

    try:
        yield app, token
    finally:
        initialize_delegation(DelegationConfig())


def test_current_workload_grant_survives_expired_person_token(signed_receiver) -> None:
    app, token = signed_receiver
    expired_person = token(
        subject="person-a", client="browser", expires_at=_NOW - 1, caller=False
    )
    with pytest.raises(Exception):
        oidc.decode_jwt(expired_person)

    workload = token(
        subject="runtime-subject", client="runtime-client", expires_at=_NOW + 300
    )
    with TestClient(app) as client:
        response = client.get(
            "/documents",
            params={"person": "person-a", "run": "run-a", "agent": "agent-a"},
            headers={"Authorization": f"Bearer {workload}"},
        )

    assert response.status_code == 200
    assert response.json() == {"subject": "person-a", "roles": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "marked", "stops"),
    [(403, False, True), (503, True, True), (503, False, False)],
)
async def test_mounted_mcp_inner_refusal_stops_before_adapter_conversion(
    status_code: int, marked: bool, stops: bool
) -> None:
    pytest.importorskip("fastapi_mcp")
    from fred_core.security.mcp_delegation_fastapi import DelegatedFastApiMCP
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    app = FastAPI()

    @app.get("/protected", operation_id="read_protected")
    async def protected() -> None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status_code,
            detail="synthetic-identifier",
            headers={"X-Fred-Denial-Cause": "standing_unavailable"} if marked else None,
        )

    inner_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test.invalid"
    )
    mount = DelegatedFastApiMCP(app, http_client=inner_client)
    mount.mount_http(app)
    interceptor = DelegatedAuthorityInterceptor(
        static_person_provider("synthetic-token"),
        delegated_server_ids={"mounted"},
    )

    def client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    async with app.router.lifespan_context(app):
        async with streamablehttp_client(
            "http://test.invalid/mcp", httpx_client_factory=client_factory
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(_request: MCPToolCallRequest):
                    return await session.call_tool("read_protected", {})

                request = MCPToolCallRequest(
                    name="read_protected", args={}, server_name="mounted"
                )
                if stops:
                    with pytest.raises(AuthorityLostError):
                        await interceptor(request, call)
                else:
                    result = await interceptor(request, call)
                    assert result.isError is True
    await inner_client.aclose()


def test_receiver_rejects_expired_workload_bearer(signed_receiver) -> None:
    app, token = signed_receiver
    workload = token(
        subject="runtime-subject",
        client="runtime-client",
        expires_at=_NOW - 1,
    )
    with TestClient(app) as client:
        response = client.get(
            "/documents",
            params={"person": "person-a", "run": "run-a", "agent": "agent-a"},
            headers={"Authorization": f"Bearer {workload}"},
        )

    assert response.status_code == 401


@pytest.mark.parametrize("subject", ["runtime-subject", "any-other-service-account"])
def test_any_role_holder_speaks_for_the_person_whatever_its_subject(
    signed_receiver, subject: str
) -> None:
    app, token = signed_receiver
    workload = token(subject=subject, client="some-workload", expires_at=_NOW + 300)
    with TestClient(app) as client:
        response = client.get(
            "/documents",
            params={"person": "person-a", "run": "run-a", "agent": "agent-a"},
            headers={"Authorization": f"Bearer {workload}"},
        )

    assert response.status_code == 200
    assert response.json() == {"subject": "person-a", "roles": []}


def test_a_grant_from_a_workload_without_the_role_is_refused(signed_receiver) -> None:
    app, token = signed_receiver
    workload = token(
        subject="runtime-subject",
        client="runtime-client",
        expires_at=_NOW + 300,
        caller=False,
    )
    with TestClient(app) as client:
        refused = client.get(
            "/documents",
            params={"person": "person-a", "run": "run-a", "agent": "agent-a"},
            headers={"Authorization": f"Bearer {workload}"},
        )
        served = client.get(
            "/documents", headers={"Authorization": f"Bearer {workload}"}
        )

    assert refused.status_code == 403
    assert refused.json()["detail"] == "delegation_not_allowed"
    assert served.status_code == 200
    assert served.json()["subject"] == "runtime-subject"
