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

import secrets

import pytest
from pydantic import AnyUrl

from knowledge_flow_backend.application_context import ApplicationContext

_REQUIRED_VARIABLE = "KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET"


def test_oidc_issuer_does_not_need_keycloak_realm_path(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    configuration = app_context.configuration.model_copy(deep=True)
    configuration.security.user.provider = "oidc"
    configuration.security.user.enabled = True
    configuration.security.user.realm_url = AnyUrl("https://identity.example/tenant/v2.0")
    monkeypatch.setenv(_REQUIRED_VARIABLE, secrets.token_urlsafe())
    monkeypatch.setattr(ApplicationContext, "_instance", None)

    ApplicationContext(configuration)


def test_keycloak_issuer_still_requires_realm_path(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    configuration = app_context.configuration.model_copy(deep=True)
    configuration.security.user.provider = "keycloak"
    configuration.security.user.enabled = True
    configuration.security.user.realm_url = AnyUrl("https://identity.example/tenant/v2.0")
    monkeypatch.setenv(_REQUIRED_VARIABLE, secrets.token_urlsafe())
    monkeypatch.setattr(ApplicationContext, "_instance", None)

    with pytest.raises(ValueError, match="Invalid Keycloak URL"):
        ApplicationContext(configuration)
