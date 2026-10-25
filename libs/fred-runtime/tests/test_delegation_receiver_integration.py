from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.delegation import (
    DelegationConfig,
    enforce_account_status,
    initialize_delegation,
)
from fred_core.security.oidc import get_current_user_without_gcu
from fred_core.tests.security.rebac_fakes import (
    AccountStatusStore,
    account_status_engine,
)

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


@asynccontextmanager
async def _serving(_app: FastAPI) -> AsyncIterator[None]:
    # A receiver installs the engine for the account status check once it is configured.
    await enforce_account_status(account_status_engine(AccountStatusStore()))
    yield


@pytest.fixture
def signed_receiver(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://issuer.test/realms/fred"
    login_client = "app"
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "KEYCLOAK_URL", issuer)
    monkeypatch.setattr(oidc, "_REALM_ISSUERS", frozenset({issuer}))
    monkeypatch.setattr(oidc, "KEYCLOAK_CLIENT_ID", login_client)
    monkeypatch.setattr(oidc, "USER_AUDIENCE", login_client)
    monkeypatch.setattr(oidc, "USER_ISSUER", issuer)
    monkeypatch.setattr(oidc, "USER_SECURITY_CONFIG", None)
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

    app = FastAPI(lifespan=_serving)

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
