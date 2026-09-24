from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from fred_core.security.delegation import DelegationConfig, preserved_delegation

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.main import _require_delegation_standing, create_app


class _Context:
    def __init__(self, rebac: Any = None, *, error: Exception | None = None) -> None:
        self.rebac = rebac
        self.error = error

    def get_rebac_engine(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.rebac


class _StandingChecked(Exception):
    pass


@pytest.mark.asyncio
async def test_delegation_startup_validates_model_and_readiness() -> None:
    rebac = SimpleNamespace(
        enforces_standing=True,
        validate_standing_model=AsyncMock(),
        is_standing_seed_ready=AsyncMock(return_value=True),
    )
    context = _Context(rebac)

    await _require_delegation_standing(context, enabled=True)

    rebac.validate_standing_model.assert_awaited_once_with()
    rebac.is_standing_seed_ready.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_delegation_startup_requires_ready_standing() -> None:
    rebac = SimpleNamespace(
        enforces_standing=True,
        validate_standing_model=AsyncMock(),
        is_standing_seed_ready=AsyncMock(return_value=False),
    )
    context = _Context(rebac)

    with pytest.raises(ValueError, match="not ready"):
        await _require_delegation_standing(context, enabled=True)


@pytest.mark.asyncio
async def test_disabled_delegation_does_not_require_rebac() -> None:
    context = _Context(error=AssertionError("must not resolve ReBAC"))

    await _require_delegation_standing(context, enabled=False)


@pytest.mark.parametrize(
    ("delegation", "expected"),
    [
        (DelegationConfig(act_for_people=True), True),
        (DelegationConfig(accept_delegated_calls=True), True),
        (DelegationConfig(), False),
    ],
    ids=["act_for_people", "accept_delegated_calls", "off"],
)
def test_app_startup_checks_standing_when_either_switch_is_on(
    app_context: ApplicationContext,
    monkeypatch,
    delegation: DelegationConfig,
    expected: bool,
) -> None:
    config = app_context.configuration.model_copy(deep=True)
    config.security.delegation = delegation
    recorded: list[bool] = []

    # Stop startup right after the check: the rest of the lifespan needs a database.
    async def record_standing(_context: Any, *, enabled: bool) -> None:
        recorded.append(enabled)
        raise _StandingChecked

    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(main_module, "_require_delegation_standing", record_standing)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for attr_name in [
        "MonitoringController",
        "TasksController",
        "MetadataController",
        "ContentController",
        "IngestionController",
        "LibrarySyncController",
        "TagController",
        "VectorSearchController",
        "CorpusTreeController",
        "SummarizeController",
        "ExtractController",
        "ResourceController",
        "McpFilesystemController",
        "CorpusManagerController",
        "TabularController",
        "OpenSearchOpsController",
        "SchedulerController",
    ]:
        monkeypatch.setattr(main_module, attr_name, lambda *args, **kwargs: None)
    # create_app builds its own context and installs the delegation block
    # process-wide; both are put back when the test ends.
    monkeypatch.setattr(ApplicationContext, "_instance", None)
    with preserved_delegation():
        app = create_app()
        with pytest.raises(_StandingChecked), TestClient(app):
            pass

    assert recorded == [expected]
