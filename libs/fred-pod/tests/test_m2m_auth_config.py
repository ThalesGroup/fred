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
from fred_pod.security import M2MAuthConfig, M2MTokenProvider


def test_token_url_keeps_the_keycloak_default() -> None:
    config = M2MAuthConfig(
        keycloak_realm_url="https://identity.example/realms/fred",
        client_id="service",
        secret_env="SYNTHETIC_SECRET_ENV",
    )

    assert config.token_url == (
        "https://identity.example/realms/fred/protocol/openid-connect/token"
    )


def test_token_url_uses_the_explicit_override() -> None:
    config = M2MAuthConfig(
        keycloak_realm_url="https://identity.example/realms/fred",
        client_id="service",
        secret_env="SYNTHETIC_SECRET_ENV",
        token_url_override="https://identity.example/oauth2/v2.0/token",
    )

    assert config.token_url == "https://identity.example/oauth2/v2.0/token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "scope", "expected_url"),
    [
        (
            None,
            None,
            "https://identity.example/realms/fred/protocol/openid-connect/token",
        ),
        (
            "https://identity.example/oauth2/v2.0/token",
            "api://fred/.default",
            "https://identity.example/oauth2/v2.0/token",
        ),
    ],
)
async def test_provider_posts_to_configured_endpoint_with_scope(
    monkeypatch: pytest.MonkeyPatch,
    override: str | None,
    scope: str | None,
    expected_url: str,
) -> None:
    monkeypatch.setenv("SYNTHETIC_SECRET_ENV", "generated-test-secret")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"access_token": "synthetic-token", "expires_in": 60}
        )

    config = M2MAuthConfig(
        keycloak_realm_url="https://identity.example/realms/fred",
        client_id="service",
        secret_env="SYNTHETIC_SECRET_ENV",
        scope=scope,
        token_url_override=override,
    )
    provider = M2MTokenProvider(config, transport=httpx.MockTransport(handle))

    assert await provider.get_token() == "synthetic-token"
    assert len(requests) == 1
    assert str(requests[0].url) == expected_url
    form = dict(httpx.QueryParams(requests[0].content.decode()))
    assert form == {
        "grant_type": "client_credentials",
        "client_id": "service",
        "client_secret": "generated-test-secret",
        **({"scope": scope} if scope else {}),
    }
