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
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.rebac.authorization_binding import AuthorizationBinding
from fred_core.security.structure import OpenFgaRebacConfig
from fred_runtime.app import agent_app, security
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
    config.security.rebac = OpenFgaRebacConfig.model_validate(
        {"api_url": "http://fga.invalid"}
    )
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
    binding = AuthorizationBinding("fred", "published-store", "published-model")
    read = AsyncMock(return_value=binding)
    validate = AsyncMock(return_value=binding)
    monkeypatch.setattr(security, "read_authorization_binding", read)
    monkeypatch.setattr(security, "validate_authorization_binding", validate)
    engine = SimpleNamespace(get_client=AsyncMock(), close=AsyncMock())
    factory = Mock(return_value=engine)
    monkeypatch.setattr(agent_app, "PublishedOpenFgaRebacEngine", factory)
    return SimpleNamespace(
        config=config,
        container=container,
        sql=sql,
        read=read,
        validate=validate,
        engine=engine,
        factory=factory,
        binding=binding,
    )


def boot(state):
    return TestClient(agent_app.create_agent_app(registry={}, config=state.config))


def test_lifespan_pins_the_published_binding_and_closes_resources(startup):
    with boot(startup):
        assert get_runtime_context().config.rebac_engine is startup.engine
        startup.read.assert_awaited_once_with(
            startup.sql, expected_configured_store="fred"
        )
        startup.validate.assert_awaited_once_with(
            startup.binding, startup.config.security.rebac
        )
        assert startup.factory.call_args.args == (
            startup.config.security.rebac,
            startup.binding,
        )
        startup.engine.get_client.assert_awaited_once()
        startup.engine.close.assert_not_awaited()
    startup.engine.close.assert_awaited_once()
    startup.sql.dispose.assert_awaited_once()


@pytest.mark.parametrize("field", ["profile", "user", "m2m", "rebac"])
def test_lifespan_refuses_missing_hardened_prerequisites(startup, field):
    security = startup.config.security
    if field == "profile":
        security.profile = None
    elif field == "rebac":
        security.rebac = None
    else:
        getattr(security, field).enabled = False
    with pytest.raises(ValueError):
        with boot(startup):
            pytest.fail("insecure startup must fail")
    startup.read.assert_not_awaited()
    startup.factory.assert_not_called()
    startup.sql.dispose.assert_awaited_once()


@pytest.mark.parametrize("timeout", [None, 0, -1, 30001])
def test_lifespan_requires_bounded_fga_timeout(startup, timeout):
    startup.config.security.rebac.timeout_millisec = timeout
    with pytest.raises(ValueError, match="timeout_millisec"):
        with boot(startup):
            pytest.fail("unbounded authorization must fail")
    startup.read.assert_not_awaited()


def test_lifespan_refuses_sqlite_authorization(startup):
    startup.sql.dialect.name = "sqlite"
    with pytest.raises(ValueError, match="shared PostgreSQL"):
        with boot(startup):
            pytest.fail("SQLite is not the Weaver authority")
    startup.read.assert_not_awaited()
    startup.sql.dispose.assert_awaited_once()


@pytest.mark.parametrize("stage", ["read", "validate"])
def test_binding_or_model_failure_prevents_readiness(startup, stage):
    getattr(startup, stage).side_effect = RuntimeError("publication unavailable")
    with pytest.raises(RuntimeError, match="publication unavailable"):
        with boot(startup):
            pytest.fail("unvalidated publication must fail")
    startup.factory.assert_not_called()
    startup.sql.dispose.assert_awaited_once()


def test_fga_client_failure_closes_both_resources(startup):
    startup.engine.get_client.side_effect = RuntimeError("transport unavailable")
    with pytest.raises(RuntimeError, match="transport unavailable"):
        with boot(startup):
            pytest.fail("unavailable transport must fail")
    startup.engine.close.assert_awaited_once()
    startup.sql.dispose.assert_awaited_once()
