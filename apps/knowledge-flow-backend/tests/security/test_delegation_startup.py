import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fred_core import AccountStatusError
from fred_core.security.delegation import DelegationConfig, enforce_account_status, initialize_delegation, preserved_delegation, require_active_subject
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from fred_core.security.structure import KeycloakUser, OpenFgaRebacConfig
from openfga_sdk.api_client import ApiClient
from openfga_sdk.configuration import Configuration

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.main import create_app

_PERSON = KeycloakUser(uid="synthetic-person", username="synthetic", roles=[])


class _ModelOnlyOpenFga:
    """OpenFGA client that serves one authorization model, answers account status Checks
    with "not suspended", records tuple writes and offers nothing else."""

    def __init__(self, model: dict) -> None:
        self.model = model
        self.writes: list[Any] = []
        self.checks: list[tuple[str, str, str]] = []

    async def read_latest_authorization_model(self):
        payload = {"authorization_model": {"id": "synthetic-latest", **self.model}}
        async with ApiClient(Configuration(api_url="http://fake-openfga:8080")) as api:
            return api.deserialize(SimpleNamespace(data=json.dumps(payload)), "ReadAuthorizationModelResponse")

    async def check(self, body, options):
        self.checks.append((body.user, body.relation, body.object))
        return SimpleNamespace(allowed=False)

    async def write(self, body, options):
        self.writes.append(body)
        return SimpleNamespace()


def _engine(client: _ModelOnlyOpenFga) -> OpenFgaRebacEngine:
    engine = OpenFgaRebacEngine(
        OpenFgaRebacConfig(api_url="http://fake-openfga:8080"),  # pyright: ignore[reportArgumentType]
        token="synthetic-test-token",  # nosec B106
        requires_active_accounts=True,
    )
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


def _allow_list_model() -> dict:
    """A platform that lists active people and defines no `suspended` relation."""
    model = json.loads(DEFAULT_SCHEMA)
    platform = next(t for t in model["type_definitions"] if t["type"] == "platform")
    del platform["relations"]["suspended"]
    del platform["metadata"]["relations"]["suspended"]
    platform["relations"]["active"] = {"this": {}}
    platform["metadata"]["relations"]["active"] = {"directly_related_user_types": [{"type": "user"}]}
    return model


class _StartupCheckRan(Exception):
    pass


@pytest.mark.asyncio
async def test_delegation_startup_validates_the_shipped_model_and_writes_nothing() -> None:
    client = _ModelOnlyOpenFga(json.loads(DEFAULT_SCHEMA))

    with preserved_delegation():
        initialize_delegation(DelegationConfig(accept_delegated_calls=True))
        await enforce_account_status(_engine(client))

    assert client.writes == []


@pytest.mark.asyncio
async def test_delegation_startup_refuses_a_model_without_suspended() -> None:
    client = _ModelOnlyOpenFga(_allow_list_model())

    with preserved_delegation():
        initialize_delegation(DelegationConfig(accept_delegated_calls=True))
        with pytest.raises(RuntimeError, match=r"^Account status authorization model is not available\.$"):
            await enforce_account_status(_engine(client))

    assert client.writes == []


@pytest.mark.parametrize(
    "delegation",
    [DelegationConfig(act_for_people=True), DelegationConfig(accept_delegated_calls=True), DelegationConfig()],
    ids=["act_for_people", "accept_delegated_calls", "off"],
)
@pytest.mark.parametrize("local_directory", [False, True])
def test_app_startup_installs_the_engine_when_account_status_is_required(
    app_context: ApplicationContext,
    monkeypatch,
    delegation: DelegationConfig,
    local_directory: bool,
) -> None:
    config = app_context.configuration.model_copy(deep=True)
    config.security.delegation = delegation
    config.security.user_directory = "local" if local_directory else "keycloak"
    client = _ModelOnlyOpenFga(json.loads(DEFAULT_SCHEMA))
    built: list[OpenFgaRebacEngine] = []

    def build_engine(_context: Any) -> OpenFgaRebacEngine:
        built.append(_engine(client))
        return built[-1]

    # Stop startup right after the account status step: the rest of the lifespan needs a database.
    def stop(_context: Any) -> None:
        raise _StartupCheckRan

    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(ApplicationContext, "get_pg_async_engine", stop)
    monkeypatch.setattr(ApplicationContext, "get_rebac_engine", build_engine)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for attr_name in [name for name in vars(main_module) if name.endswith("Controller")]:
        monkeypatch.setattr(main_module, attr_name, lambda *args, **kwargs: None)
    # create_app builds its own context and installs the delegation block
    # process-wide; both are put back when the test ends.
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    with preserved_delegation():
        app = create_app()
        with pytest.raises(_StartupCheckRan), TestClient(app):
            pass
        # The request's account status check reaches the engine startup installed.
        asyncio.run(require_active_subject(_PERSON))

    required = delegation.in_use or local_directory
    assert len(built) == (1 if required else 0)
    assert client.checks == ([("user:synthetic-person", "suspended", "platform:fred")] if required else [])
    assert client.writes == []


@pytest.mark.parametrize("local_directory", [False, True])
def test_app_startup_refuses_a_model_without_suspended(app_context: ApplicationContext, monkeypatch, local_directory: bool) -> None:
    config = app_context.configuration.model_copy(deep=True)
    config.security.delegation = DelegationConfig(accept_delegated_calls=not local_directory)
    config.security.user_directory = "local" if local_directory else "keycloak"
    client = _ModelOnlyOpenFga(_allow_list_model())

    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(ApplicationContext, "get_rebac_engine", lambda _context: _engine(client))
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for attr_name in [name for name in vars(main_module) if name.endswith("Controller")]:
        monkeypatch.setattr(main_module, attr_name, lambda *args, **kwargs: None)
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    with preserved_delegation():
        app = create_app()
        with pytest.raises(RuntimeError, match=r"^Account status authorization model is not available\.$"), TestClient(app):
            pass
        with pytest.raises(AccountStatusError) as refused:
            asyncio.run(require_active_subject(_PERSON))

    assert refused.value.unavailable is True
    assert client.writes == []
