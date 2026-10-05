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

"""Real signed tokens with a mock JWKS, for Keycloak and generic OIDC shapes."""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fred_pod.security.oidc_endpoints import resolve_endpoints
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm
from pydantic import AnyHttpUrl, AnyUrl

from fred_core.security import oidc
from fred_core.security.structure import (
    KeycloakUser,
    UserClaims,
    UserSecurity,
    is_service_agent,
)

REALM = "http://localhost:8080/realms/app"
ISSUER = "https://login.microsoftonline.com/example-tenant/v2.0"
JWKS_URL = "https://identity.example/keys"
ENDPOINT_URL = "https://identity.example/token"
API_AUDIENCE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PERSON_ID = "b672a4f0-c986-46df-ac3d-d16c26b06741"
KID = "local-test-key"


@pytest.fixture(autouse=True)
def preserve_security_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    resolve_endpoints.cache_clear()
    for name in (
        "KEYCLOAK_ENABLED",
        "KEYCLOAK_URL",
        "KEYCLOAK_JWKS_URL",
        "KEYCLOAK_CLIENT_ID",
        "USER_AUDIENCE",
        "USER_ISSUER",
        "USER_TOKEN_ENDPOINT",
        "USER_SECURITY_CONFIG",
        "_JWKS_CLIENT",
        "_REALM_ISSUERS",
        "STRICT_ISSUER",
        "STRICT_AUDIENCE",
    ):
        monkeypatch.setattr(oidc, name, getattr(oidc, name))
    monkeypatch.setattr(oidc, "STRICT_ISSUER", True)
    monkeypatch.setattr(oidc, "STRICT_AUDIENCE", True)
    yield


@pytest.fixture
def signed_tokens(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = KID
    fetch_urls: list[str] = []

    def fetch_data(client: PyJWKClient) -> dict:
        fetch_urls.append(client.uri)
        return {"keys": [jwk]}

    monkeypatch.setattr(PyJWKClient, "fetch_data", fetch_data)

    def sign(issuer: str, audience: str, **claims: object) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": issuer, "aud": audience, "iat": now, "exp": now + 300, **claims},
            private_key,
            algorithm="RS256",
            headers={"kid": KID},
        )

    return sign, fetch_urls


def test_keycloak_token_builds_the_same_user(signed_tokens) -> None:
    sign, fetch_urls = signed_tokens
    oidc.initialize_user_security(
        UserSecurity(realm_url=AnyUrl(REALM), client_id="app")
    )
    oidc._REALM_ISSUERS = frozenset({REALM})
    token = sign(
        REALM,
        "app",
        sub=PERSON_ID,
        preferred_username="alice",
        email="alice@example.test",
        azp="app",
        resource_access={"app": {"roles": ["viewer"]}},
    )

    user = oidc.decode_jwt(token)

    assert user == KeycloakUser(
        uid=PERSON_ID,
        username="alice",
        roles=["viewer"],
        email="alice@example.test",
        client_id="app",
        token_issuer=REALM,
        token_audiences=frozenset({"app"}),
    )
    assert fetch_urls == [f"{REALM}/protocol/openid-connect/certs"]


def test_entra_shaped_token_uses_api_audience_oid_and_flat_app_roles(
    signed_tokens, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign, fetch_urls = signed_tokens

    def discovery(url: str, *, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "issuer": ISSUER,
                "jwks_uri": JWKS_URL,
                "token_endpoint": ENDPOINT_URL,
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", discovery)
    oidc.initialize_user_security(
        UserSecurity(
            realm_url=AnyUrl(ISSUER),
            client_id="fred-ui",
            provider="oidc",
            audience=API_AUDIENCE,
            roles_claim=["roles"],
            claims=UserClaims(uid="oid"),
        )
    )
    oidc._REALM_ISSUERS = frozenset({ISSUER})
    claims = {
        "sub": "entra-pairwise-subject",
        "oid": PERSON_ID,
        "azp": "fred-ui",
        "preferred_username": "alice@example.test",
        "roles": ["service_agent"],
    }

    user = oidc.decode_jwt(sign(ISSUER, API_AUDIENCE, **claims))

    assert user.uid == PERSON_ID
    assert user.username == "alice@example.test"
    assert user.roles == ["service_agent"]
    assert user.client_id == "fred-ui"
    assert is_service_agent(user)
    assert fetch_urls == [JWKS_URL]

    with pytest.raises(HTTPException) as exc:
        oidc.decode_jwt(sign(ISSUER, "fred-ui", **claims))
    assert exc.value.status_code == 401


def test_selected_admission_attribute_is_signature_verified_and_hidden(
    signed_tokens, monkeypatch
):
    from fred_pod.security.structure import PlatformAccessConfiguration

    from fred_core.security.platform_access import access_control

    sign, _ = signed_tokens
    monkeypatch.setattr(
        access_control,
        "_configured",
        PlatformAccessConfiguration(
            enabled=True,
            jwt_claim=["profile", "unit"],
            accepted_regex="accepted",
            supportLink=AnyHttpUrl("https://support.example.org"),
        ),
    )
    oidc.initialize_user_security(
        UserSecurity(realm_url=AnyUrl(REALM), client_id="app")
    )
    oidc._REALM_ISSUERS = frozenset({REALM})
    user = oidc.decode_jwt(
        sign(REALM, "app", sub=PERSON_ID, profile={"unit": ["other", "accepted"]})
    )
    assert user.admission_attribute == ["other", "accepted"]
    assert user.admission_issued_at is not None
    assert user.admission_expires_at is not None
    assert user.admission_expires_at > user.admission_issued_at
    assert "admission_attribute" not in user.model_dump()
    assert "accepted" not in repr(user)
