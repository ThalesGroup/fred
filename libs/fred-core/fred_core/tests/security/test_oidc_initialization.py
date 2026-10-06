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

import httpx
import pytest
from fred_pod.security.oidc_endpoints import resolve_endpoints
from pydantic import AnyHttpUrl, AnyUrl

from fred_core import get_token_endpoint
from fred_core.security import oidc
from fred_core.security.structure import UserSecurity

REALM = "http://localhost:8080/realms/app"
ISSUER = "https://identity.example/tenant/v2.0"
JWKS = "https://identity.example/keys"
ENDPOINT_URL = "https://identity.example/token"


@pytest.fixture(autouse=True)
def preserve_security_state(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ):
        monkeypatch.setattr(oidc, name, getattr(oidc, name))


def test_keycloak_initialization_keeps_existing_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_request(*args: object, **kwargs: object) -> None:
        pytest.fail("Keycloak startup must not discover endpoints")

    monkeypatch.setattr(httpx, "get", unexpected_request)
    oidc.initialize_user_security(
        UserSecurity(realm_url=AnyUrl(REALM), client_id="app")
    )

    assert oidc.KEYCLOAK_URL == REALM
    assert oidc.KEYCLOAK_JWKS_URL == f"{REALM}/protocol/openid-connect/certs"
    assert oidc.USER_ISSUER == REALM
    assert oidc.USER_AUDIENCE == "app"
    assert get_token_endpoint() == f"{REALM}/protocol/openid-connect/token"


def test_oidc_initialization_discovers_endpoints_without_parsing_a_realm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, float]] = []

    def get(url: str, *, timeout: float) -> httpx.Response:
        requests.append((url, timeout))
        return httpx.Response(
            200,
            json={"issuer": ISSUER, "jwks_uri": JWKS, "token_endpoint": ENDPOINT_URL},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(
        oidc, "split_realm_url", lambda url: pytest.fail("OIDC is not a Keycloak realm")
    )
    config = UserSecurity(
        realm_url=AnyUrl(ISSUER),
        client_id="app",
        provider="oidc",
        audience="fred-api",
        roles_claim=["roles"],
    )
    oidc.initialize_user_security(config)

    assert requests == [(f"{ISSUER}/.well-known/openid-configuration", 5.0)]
    assert oidc.KEYCLOAK_JWKS_URL == JWKS
    assert oidc.USER_ISSUER == ISSUER
    assert oidc.USER_AUDIENCE == "fred-api"
    assert oidc.USER_SECURITY_CONFIG is config
    assert get_token_endpoint() == ENDPOINT_URL


def test_oidc_initialization_passes_explicit_endpoint_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout: httpx.Response(
            200,
            json={"issuer": ISSUER, "jwks_uri": JWKS, "token_endpoint": ENDPOINT_URL},
            request=httpx.Request("GET", url),
        ),
    )
    override_url = "https://override.example/token"
    oidc.initialize_user_security(
        UserSecurity(
            realm_url=AnyUrl(ISSUER),
            client_id="app",
            provider="oidc",
            jwks_url=AnyHttpUrl("https://override.example/keys"),
            token_url=AnyHttpUrl(override_url),
        )
    )

    assert oidc.KEYCLOAK_JWKS_URL == "https://override.example/keys"
    assert get_token_endpoint() == "https://override.example/token"
