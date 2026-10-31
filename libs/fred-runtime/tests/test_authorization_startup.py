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

"""Production pod lifespan prerequisites, without the offline route fixture."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_runtime.app import agent_app
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.runtime_context import get_runtime_context


@pytest.fixture
def startup(monkeypatch, minimal_config, restore_pod_security):
    config = minimal_config.model_copy(deep=True)
    config.security.profile = "c3"
    config.security.user.realm_url = "http://localhost/realms/test"
    config.security.m2m.realm_url = "http://localhost/realms/test"
    config.security.user.enabled = True
    config.security.m2m.enabled = True
    for name in ("KEYCLOAK_ENABLED", "STRICT_ISSUER", "STRICT_AUDIENCE"):
        monkeypatch.setattr(oidc, name, getattr(oidc, name))
    container = PodApplicationContext(config)
    sql = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), dispose=AsyncMock()
    )
    monkeypatch.setattr(container, "_sql_engine", sql)
    # The fake engine runs no SQL; steering cleanup has its own tests.
    monkeypatch.setattr(agent_app.turn_steering_mailbox, "cleanup_expired", AsyncMock())
    monkeypatch.setattr(container, "initialize_sql", AsyncMock())
    monkeypatch.setattr(container, "initialize_filesystem", AsyncMock())
    monkeypatch.setattr(container, "get_filesystem", lambda: SimpleNamespace())
    monkeypatch.setattr(agent_app, "build_pod_container", lambda _: container)
    monkeypatch.setattr(agent_app, "_build_chat_model_factory", lambda _: None)
    return SimpleNamespace(config=config, container=container, sql=sql)


def boot(state):
    return TestClient(agent_app.create_agent_app(registry={}, config=state.config))


def test_lifespan_initializes_sql_and_closes_resources(startup):
    with boot(startup):
        startup.container.initialize_sql.assert_awaited_once()
        assert get_runtime_context().config.control_plane_http_client is not None
    startup.sql.dispose.assert_awaited_once()


@pytest.mark.parametrize("field", ["profile", "user", "m2m"])
def test_lifespan_refuses_missing_hardened_prerequisites(startup, field):
    security = startup.config.security
    if field == "profile":
        security.profile = None
    else:
        getattr(security, field).enabled = False
    with pytest.raises(ValueError):
        with boot(startup):
            pytest.fail("insecure startup must fail")
    startup.sql.dispose.assert_awaited_once()


def test_lifespan_refuses_sqlite_authorization(startup):
    startup.sql.dialect.name = "sqlite"
    with pytest.raises(ValueError, match="shared PostgreSQL"):
        with boot(startup):
            pytest.fail("SQLite is not the Weaver authority")
    startup.sql.dispose.assert_awaited_once()
