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
from fred_pod.security.structure import SecurityConfiguration
from pydantic import ValidationError


@pytest.fixture
def legacy_security() -> dict:
    return {
        "m2m": {"realm_url": "https://id.example/realms/fred", "client_id": "service"},
        "user": {"realm_url": "https://id.example/realms/fred", "client_id": "app"},
    }


def test_existing_security_configuration_keeps_keycloak_defaults(
    legacy_security,
) -> None:
    security = SecurityConfiguration.model_validate(legacy_security)

    assert security.m2m.provider == "keycloak"
    assert security.m2m.scope is None
    assert security.m2m.token_url is None
    assert security.user.provider == "keycloak"
    assert security.user.audience is None
    assert security.user.scope is None
    assert security.user.jwks_url is None
    assert security.user.token_url is None
    assert security.user.roles_claim is None
    assert security.user.claims.model_dump() == {
        "uid": "sub",
        "username": "preferred_username",
        "email": "email",
        "given_name": "given_name",
        "family_name": "family_name",
    }
    assert security.user_directory == "keycloak"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("user", "provider"), "unknown"),
        (("m2m", "provider"), "unknown"),
        (("user_directory",), "unknown"),
    ],
)
def test_invalid_provider_or_directory_is_rejected(
    legacy_security, path, value
) -> None:
    config = {
        **legacy_security,
        "m2m": {**legacy_security["m2m"]},
        "user": {**legacy_security["user"]},
    }
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        SecurityConfiguration.model_validate(config)
