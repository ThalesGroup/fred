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

from __future__ import annotations

import httpx
import pytest
from fred_pod.security import OidcEndpoints, resolve_endpoints

ISSUER = "https://identity.example/tenant/v2.0"
JWKS = "https://identity.example/keys"
TOKEN = "https://identity.example/token"


@pytest.fixture(autouse=True)
def clear_endpoint_cache() -> None:
    resolve_endpoints.cache_clear()


def discovery_response(
    *, issuer: str = ISSUER, status_code: int = 200
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"issuer": issuer, "jwks_uri": JWKS, "token_endpoint": TOKEN},
        request=httpx.Request("GET", f"{ISSUER}/.well-known/openid-configuration"),
    )


def test_keycloak_urls_are_constructed_without_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_request(*args: object, **kwargs: object) -> None:
        pytest.fail("Keycloak must not use OIDC discovery")

    monkeypatch.setattr(httpx, "get", unexpected_request)

    assert resolve_endpoints(
        provider="keycloak", realm_url="https://identity.example/realms/fred"
    ) == OidcEndpoints(
        issuer="https://identity.example/realms/fred",
        jwks_uri="https://identity.example/realms/fred/protocol/openid-connect/certs",
        token_endpoint="https://identity.example/realms/fred/protocol/openid-connect/token",
    )


def test_oidc_discovery_uses_document_and_caches_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []

    def get(url: str, *, timeout: float) -> httpx.Response:
        calls.append((url, timeout))
        return discovery_response(issuer=f"{ISSUER}/")

    monkeypatch.setattr(httpx, "get", get)

    first = resolve_endpoints(provider="oidc", realm_url=f"{ISSUER}/")
    second = resolve_endpoints(provider="oidc", realm_url=f"{ISSUER}/")

    assert first == second == OidcEndpoints(ISSUER, JWKS, TOKEN)
    assert calls == [(f"{ISSUER}/.well-known/openid-configuration", 5.0)]


def test_explicit_oidc_endpoints_override_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: discovery_response())

    endpoints = resolve_endpoints(
        provider="oidc",
        realm_url=ISSUER,
        jwks_url="https://override.example/keys",
        token_url="https://override.example/token",
    )

    assert endpoints.jwks_uri == "https://override.example/keys"
    assert endpoints.token_endpoint == "https://override.example/token"


def test_oidc_issuer_mismatch_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: discovery_response(issuer="https://other.example"),
    )

    with pytest.raises(
        RuntimeError, match="configured.*identity.example.*discovered.*other.example"
    ):
        resolve_endpoints(provider="oidc", realm_url=ISSUER)


@pytest.mark.parametrize("status_code", [404, 503])
def test_non_200_discovery_stops_startup(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: discovery_response(status_code=status_code),
    )

    with pytest.raises(RuntimeError, match=f"HTTP {status_code}"):
        resolve_endpoints(provider="oidc", realm_url=ISSUER)


def test_discovery_timeout_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise httpx.ReadTimeout("discovery timed out")

    monkeypatch.setattr(httpx, "get", timeout)

    with pytest.raises(RuntimeError, match="OIDC discovery failed.*ReadTimeout"):
        resolve_endpoints(provider="oidc", realm_url=ISSUER, timeout_seconds=0.1)


def test_invalid_discovered_endpoint_stops_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(
        200,
        json={"issuer": ISSUER, "jwks_uri": "not a URL", "token_endpoint": TOKEN},
        request=httpx.Request("GET", f"{ISSUER}/.well-known/openid-configuration"),
    )
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="invalid jwks_uri"):
        resolve_endpoints(provider="oidc", realm_url=ISSUER)
