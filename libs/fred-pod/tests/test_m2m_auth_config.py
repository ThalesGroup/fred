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

from fred_pod.security import M2MAuthConfig


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
