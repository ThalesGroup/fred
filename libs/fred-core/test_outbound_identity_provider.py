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

import pytest
from fred_core.security.outbound import ClientCredentialsProvider


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (None, "https://identity.example/realms/fred/protocol/openid-connect/token"),
        (
            "https://identity.example/oauth2/v2.0/token",
            "https://identity.example/oauth2/v2.0/token",
        ),
    ],
)
def test_client_credentials_token_url_override(
    override: str | None, expected: str
) -> None:
    provider = ClientCredentialsProvider(
        keycloak_base="https://identity.example",
        realm="fred",
        client_id="service",
        client_secret="generated-test-secret",
        token_url=override,
    )

    assert provider.token_url == expected
