from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from knowledge_flow_backend.common.structures import PrometheusConfig
from knowledge_flow_backend.features.kpi.prometheus_service import (
    PrometheusAPIError,
    PrometheusOpsService,
)
from knowledge_flow_backend.features.kpi.prometheus_structures import (
    PrometheusQueryRangeRequest,
    PrometheusQueryRequest,
    PrometheusSeriesRequest,
)


@pytest.mark.asyncio
async def test_instant_query_serializes_body_and_auth_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "vector", "result": []}},
        )

    service = PrometheusOpsService(
        PrometheusConfig(
            base_url="http://prometheus:9090/",
            verify_ssl=False,
            timeout_seconds=12.0,
            bearer_token="secret-token",
        ),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.instant_query(PrometheusQueryRequest(query="up", time=1710000000, timeout="5s"))

    assert captured["path"] == "/api/v1/query"
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["body"] == {
        "query": ["up"],
        "time": ["1710000000"],
        "timeout": ["5s"],
    }
    assert payload["data"]["resultType"] == "vector"


@pytest.mark.asyncio
async def test_series_defaults_to_last_six_hours_when_bounds_missing() -> None:
    captured: dict[str, object] = {}
    fixed_now = datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={"status": "success", "data": ["up", "process_start_time_seconds"]},
        )

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
        now_provider=lambda: fixed_now,
    )

    await service.series(PrometheusSeriesRequest(matchers=["up"]))

    assert captured["body"] == {
        "match[]": ["up"],
        "start": ["2026-03-17T06:00:00Z"],
        "end": ["2026-03-17T12:00:00Z"],
    }


@pytest.mark.asyncio
async def test_range_query_preserves_matrix_payload() -> None:
    matrix_payload = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"__name__": "up", "job": "api"},
                    "values": [[1710000000, "1"], [1710000300, "1"]],
                }
            ],
        },
        "warnings": ["slow query"],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=matrix_payload)

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.range_query(
        PrometheusQueryRangeRequest(
            query="sum(rate(http_requests_total[5m]))",
            start="2026-03-17T11:00:00Z",
            end="2026-03-17T12:00:00Z",
            step="60s",
        )
    )

    assert payload == matrix_payload


@pytest.mark.asyncio
async def test_timeout_maps_to_prometheus_api_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom")

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=1.0),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PrometheusAPIError) as exc_info:
        await service.targets()

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == {
        "status": "error",
        "errorType": "timeout",
        "error": "Timed out while querying Prometheus.",
    }
