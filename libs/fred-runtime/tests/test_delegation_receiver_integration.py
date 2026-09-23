from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.delegation import (
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.security.oidc import get_current_user_without_gcu

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
    audience = "knowledge-flow"
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", issuer)
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", audience)
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
    monkeypatch.setattr(oidc, "_JWKS_CLIENT", _Jwks(private_key.public_key()))
    monkeypatch.setattr(jwt.api_jwt, "datetime", _FixedDateTime)
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id="runtime-client",
                    subject="runtime-subject",
                )
            ],
        ),
        issuer=issuer,
        audience=audience,
    )

    def token(*, subject: str, client: str, expires_at: int) -> str:
        return jwt.encode(
            {
                "sub": subject,
                "azp": client,
                "iss": issuer,
                "aud": audience,
                "typ": "Bearer",
                "iat": _NOW - 30,
                "exp": expires_at,
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
    expired_person = token(subject="person-a", client="browser", expires_at=_NOW - 1)
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
