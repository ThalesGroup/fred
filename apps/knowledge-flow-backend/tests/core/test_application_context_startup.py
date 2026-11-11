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

import logging
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


def test_startup_reports_its_configuration_as_one_event_without_secrets(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from knowledge_flow_backend import application_context as module

    secret = secrets.token_urlsafe()
    monkeypatch.setenv(module.POSTGRES_PASSWORD_ENV, secret)
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        ApplicationContext(app_context.configuration)

    [summary] = [record for record in caplog.records if record.name == module.__name__]
    assert summary.getMessage() == "Knowledge Flow configuration"
    assert (summary.vector_backend, summary.tabular_max_rows) == ("pgvector", app_context.configuration.storage.tabular_store.query.max_rows)
    assert secret not in str(vars(summary))
