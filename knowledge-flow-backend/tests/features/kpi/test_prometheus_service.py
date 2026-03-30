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
            bearer_token="secret-token",  # pragma: allowlist secret
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
async def test_targets_uses_basic_auth_when_configured() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"activeTargets": [], "droppedTargets": []},
            },
        )

    service = PrometheusOpsService(
        PrometheusConfig(
            base_url="http://prometheus:9090",
            timeout_seconds=12.0,
            username="alice",
            password="secret",  # pragma: allowlist secret
        ),
        transport=httpx.MockTransport(handler),
    )

    await service.targets()

    assert captured["authorization"] == "Basic YWxpY2U6c2VjcmV0"


@pytest.mark.asyncio
async def test_targets_uses_admin_as_default_basic_auth_username() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"activeTargets": [], "droppedTargets": []},
            },
        )

    service = PrometheusOpsService(
        PrometheusConfig(
            base_url="http://prometheus:9090",
            timeout_seconds=12.0,
            password="secret",  # pragma: allowlist secret
        ),
        transport=httpx.MockTransport(handler),
    )

    await service.targets()

    assert captured["authorization"] == "Basic YWRtaW46c2VjcmV0"


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
async def test_metrics_uses_metric_name_label_endpoint_and_filters_results() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    "up",
                    "process_start_time_seconds",
                    "container_cpu_usage_seconds_total",
                ],
            },
        )

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.metrics(limit=1, search="time")

    assert captured["path"] == "/api/v1/label/__name__/values"
    assert payload["data"] == ["process_start_time_seconds"]


@pytest.mark.asyncio
async def test_metrics_catalog_combines_metric_names_with_metadata() -> None:
    captured_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_paths.append(request.url.path)
        if request.url.path == "/api/v1/label/__name__/values":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        "container_cpu_usage_seconds_total",
                        "container_memory_working_set_bytes",
                    ],
                },
            )

        metric = request.url.params.get("metric")
        if metric == "container_cpu_usage_seconds_total":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        metric: [
                            {
                                "type": "counter",
                                "help": "Cumulative cpu time consumed by the container.",
                                "unit": "seconds",
                            }
                        ]
                    },
                },
            )
        if metric == "container_memory_working_set_bytes":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        metric: [
                            {
                                "type": "gauge",
                                "help": "Current working set memory.",
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url}")

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.metrics_catalog(limit=2, search="container")

    assert captured_paths == [
        "/api/v1/label/__name__/values",
        "/api/v1/metadata",
        "/api/v1/metadata",
    ]
    assert payload["data"] == [
        {
            "name": "container_cpu_usage_seconds_total",
            "type": "counter",
            "help": "Cumulative cpu time consumed by the container.",
            "unit": "seconds",
        },
        {
            "name": "container_memory_working_set_bytes",
            "type": "gauge",
            "help": "Current working set memory.",
        },
    ]


@pytest.mark.asyncio
async def test_metadata_falls_back_to_base_metric_for_histogram_suffix() -> None:
    captured_metrics: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        if metric is not None:
            captured_metrics.append(metric)
        if metric == "ingestion_document_duration_ms_bucket":
            return httpx.Response(200, json={"status": "success", "data": {}})
        if metric == "ingestion_document_duration_ms":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "ingestion_document_duration_ms": [
                            {
                                "type": "histogram",
                                "help": "KPI timer",
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"Unexpected metric lookup: {metric}")

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.metadata(
        metric="ingestion_document_duration_ms_bucket",
        limit=1,
    )

    assert captured_metrics == [
        "ingestion_document_duration_ms_bucket",
        "ingestion_document_duration_ms",
    ]
    assert payload["resolvedMetric"] == "ingestion_document_duration_ms"
    assert payload["data"]["ingestion_document_duration_ms"][0]["type"] == "histogram"
    assert payload["data"]["ingestion_document_duration_ms_bucket"][0]["help"] == "KPI timer"
    assert ("Metadata for ingestion_document_duration_ms_bucket resolved from base metric ingestion_document_duration_ms.") in payload["warnings"]


@pytest.mark.asyncio
async def test_metrics_catalog_uses_base_metric_metadata_for_histogram_suffix() -> None:
    captured_requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        captured_requests.append((request.url.path, metric))
        if request.url.path == "/api/v1/label/__name__/values":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": ["ingestion_document_duration_ms_bucket"],
                },
            )
        if metric == "ingestion_document_duration_ms_bucket":
            return httpx.Response(200, json={"status": "success", "data": {}})
        if metric == "ingestion_document_duration_ms":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "ingestion_document_duration_ms": [
                            {
                                "type": "histogram",
                                "help": "KPI timer",
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url}")

    service = PrometheusOpsService(
        PrometheusConfig(base_url="http://prometheus:9090", timeout_seconds=10.0),
        transport=httpx.MockTransport(handler),
    )

    payload = await service.metrics_catalog(limit=1, search="ingestion")

    assert captured_requests == [
        ("/api/v1/label/__name__/values", None),
        ("/api/v1/metadata", "ingestion_document_duration_ms_bucket"),
        ("/api/v1/metadata", "ingestion_document_duration_ms"),
    ]
    assert payload["data"] == [
        {
            "name": "ingestion_document_duration_ms_bucket",
            "type": "histogram",
            "help": "KPI timer",
        }
    ]


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
