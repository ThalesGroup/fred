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

from knowledge_flow_backend import application_context as application_context_module
from knowledge_flow_backend.application_context import ApplicationContext

_REQUIRED_VARIABLE = "KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET"


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_user_security_refuses_to_start_without_the_client_secret(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal names the variable; the startup log never does."""
    configuration = app_context.configuration.model_copy(deep=True)
    configuration.security.user.enabled = True
    context_logger = application_context_module.logger
    previous_level = context_logger.level
    records = _Records()
    context_logger.addHandler(records)
    context_logger.setLevel(logging.DEBUG)
    try:
        monkeypatch.delenv(_REQUIRED_VARIABLE, raising=False)
        monkeypatch.setattr(ApplicationContext, "_instance", None)
        with pytest.raises(ValueError, match=_REQUIRED_VARIABLE):
            ApplicationContext(configuration)

        monkeypatch.setenv(_REQUIRED_VARIABLE, secrets.token_urlsafe())
        monkeypatch.setattr(ApplicationContext, "_instance", None)
        ApplicationContext(configuration)
    finally:
        context_logger.removeHandler(records)
        context_logger.setLevel(previous_level)

    assert records.records
    assert all(_REQUIRED_VARIABLE not in record.getMessage() for record in records.records)
