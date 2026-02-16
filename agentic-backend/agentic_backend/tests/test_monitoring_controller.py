from typing import Any, cast

import pytest
from fastapi import HTTPException

from agentic_backend.core.monitoring.monitoring_controller import (
    get_node_numerical_metrics,
)


class _DummyUser:
    uid = "u-1"


class _DummyOrchestrator:
    async def get_metrics(self, user, start, end, precision, groupby, agg_mapping):
        raise ValueError("Invalid 'start' timestamp: 'bad'.")


@pytest.mark.asyncio
async def test_get_node_numerical_metrics_returns_400_on_invalid_bounds():
    with pytest.raises(HTTPException) as exc:
        await get_node_numerical_metrics(
            start="bad",
            end="2026-02-16T04:59:59.999Z",
            precision="hour",
            agg=[],
            groupby=[],
            user=cast(Any, _DummyUser()),
            session_orchestrator=cast(Any, _DummyOrchestrator()),
        )

    assert exc.value.status_code == 400
    assert "Invalid 'start' timestamp" in str(exc.value.detail)
