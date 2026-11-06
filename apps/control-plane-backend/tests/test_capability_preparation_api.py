"""Authorization and bounded API contracts for generic preparation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fred_core import TeamPermission
from fred_core.common import TeamId
from pydantic import ValidationError

from control_plane_backend.capability_preparations import api
from control_plane_backend.capability_preparations.schemas import (
    PreparationStatusPage,
)


@pytest.mark.asyncio
async def test_team_status_requires_editor_permission_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deny = AsyncMock(side_effect=HTTPException(status_code=403))
    read = AsyncMock()
    monkeypatch.setattr(api, "require_team_access", deny)
    monkeypatch.setattr(api, "list_agent_preparations", read)
    deps = cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace()))
    with pytest.raises(HTTPException) as error:
        await api.get_team_agent_preparations(
            TeamId("t1"), "a1", deps, limit=32, offset=0, user=cast(Any, object())
        )
    assert error.value.status_code == 403
    assert deny.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_UPDATE_AGENTS
    ]
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_work_is_scoped_to_configured_runtime_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require = Mock(return_value=True)
    monkeypatch.setattr(api, "is_service_agent", require)
    row = SimpleNamespace(runtime_id="fred-agents")
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    source = SimpleNamespace(
        runtime_id="fred-agents", enabled=True, preparation_client_id="agentic"
    )
    deps = cast(
        Any,
        SimpleNamespace(
            configuration=SimpleNamespace(
                security=SimpleNamespace(m2m=SimpleNamespace(enabled=True)),
                platform=SimpleNamespace(runtime_catalog_sources=[source]),
            )
        ),
    )
    wrong = cast(Any, SimpleNamespace(caller=SimpleNamespace(client_id="other")))
    with pytest.raises(HTTPException) as error:
        await api._require_worker(session, deps, wrong, "prep-1")
    assert error.value.status_code == 404
    right = cast(Any, SimpleNamespace(caller=SimpleNamespace(client_id="agentic")))
    assert await api._require_worker(session, deps, right, "prep-1") is row
    assert require.call_count == 2


def test_status_page_refuses_unbounded_results() -> None:
    with pytest.raises(ValidationError):
        PreparationStatusPage.model_validate({"items": [{}] * 101})
