from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import Action, BaseUserStore, Resource, UserRow, get_config
from fred_core.users.store.postgres_user_store import get_user_store

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.common.structures import IntegrationsConfig, PrometheusConfig
from knowledge_flow_backend.features.kpi import prometheus_controller as prom_controller_module
from knowledge_flow_backend.features.kpi.prometheus_controller import PrometheusOpsController
from knowledge_flow_backend.main import create_app

fake_user = UserRow(id=uuid4(), gcuVersionAccepted=None, gcuAcceptedAt=datetime.now())


def _build_prometheus_app(application_context, base_url: str = "") -> TestClient:
    router = APIRouter(prefix=base_url)
    PrometheusOpsController(router)
    mock_store = AsyncMock(spec=BaseUserStore)
    mock_store.find_user_by_id.return_value = fake_user
    app = FastAPI()
    app.dependency_overrides[get_config] = get_configuration
    app.dependency_overrides[get_user_store] = lambda: mock_store
    app.include_router(router)
    return TestClient(app)


def test_prometheus_query_uses_metrics_resource_and_returns_payload(
    app_context: ApplicationContext,
    monkeypatch,
) -> None:
    app_context.configuration.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )
    observed: dict[str, object] = {}

    def fake_authorize(user, action, resource) -> None:
        observed["action"] = action
        observed["resource"] = resource

    async def fake_instant_query(self, body):
        observed["query"] = body.query
        return {"status": "success", "data": {"resultType": "vector", "result": []}}

    monkeypatch.setattr(prom_controller_module, "authorize_or_raise", fake_authorize)
    monkeypatch.setattr(
        prom_controller_module.PrometheusOpsService,
        "instant_query",
        fake_instant_query,
    )

    with _build_prometheus_app(app_context) as client:
        response = client.post("/prometheus/query", json={"query": "up"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert observed == {
        "action": Action.READ,
        "resource": Resource.METRICS,
        "query": "up",
    }


def test_prometheus_query_rejects_blank_query(
    app_context: ApplicationContext,
) -> None:
    app_context.configuration.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )

    with _build_prometheus_app(app_context) as client:
        response = client.post("/prometheus/query", json={"query": "   "})

    assert response.status_code == 422
    assert "must not be empty" in response.text


def test_prometheus_label_values_forwards_matchers(
    app_context: ApplicationContext,
    monkeypatch,
) -> None:
    app_context.configuration.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )
    observed: dict[str, object] = {}

    async def fake_label_values(self, label_name, *, start, end, matchers):
        observed["label_name"] = label_name
        observed["start"] = start
        observed["end"] = end
        observed["matchers"] = matchers
        return {"status": "success", "data": ["prod", "staging"]}

    monkeypatch.setattr(
        prom_controller_module.PrometheusOpsService,
        "label_values",
        fake_label_values,
    )

    with _build_prometheus_app(app_context) as client:
        response = client.get(
            "/prometheus/labels/namespace/values",
            params=[("match[]", 'up{job="kubelet"}'), ("match[]", "up")],
        )

    assert response.status_code == 200
    assert response.json()["data"] == ["prod", "staging"]
    assert observed == {
        "label_name": "namespace",
        "start": None,
        "end": None,
        "matchers": ['up{job="kubelet"}', "up"],
    }


def test_prometheus_metrics_forwards_limit_and_search(
    app_context: ApplicationContext,
    monkeypatch,
) -> None:
    app_context.configuration.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )
    observed: dict[str, object] = {}

    async def fake_metrics(self, *, limit, search):
        observed["limit"] = limit
        observed["search"] = search
        return {"status": "success", "data": ["process_start_time_seconds"]}

    monkeypatch.setattr(
        prom_controller_module.PrometheusOpsService,
        "metrics",
        fake_metrics,
    )

    with _build_prometheus_app(app_context) as client:
        response = client.get(
            "/prometheus/metrics",
            params={"limit": 25, "search": "time"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == ["process_start_time_seconds"]
    assert observed == {"limit": 25, "search": "time"}


def test_prometheus_metrics_catalog_forwards_limit_and_search(
    app_context: ApplicationContext,
    monkeypatch,
) -> None:
    app_context.configuration.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )
    observed: dict[str, object] = {}

    async def fake_metrics_catalog(self, *, limit, search):
        observed["limit"] = limit
        observed["search"] = search
        return {
            "status": "success",
            "data": [
                {"name": "process_start_time_seconds", "type": "gauge"},
            ],
        }

    monkeypatch.setattr(
        prom_controller_module.PrometheusOpsService,
        "metrics_catalog",
        fake_metrics_catalog,
    )

    with _build_prometheus_app(app_context) as client:
        response = client.get(
            "/prometheus/metrics_catalog",
            params={"limit": 10, "search": "time"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"name": "process_start_time_seconds", "type": "gauge"},
    ]
    assert observed == {"limit": 10, "search": "time"}


def test_create_app_mounts_prometheus_mcp_when_enabled(
    app_context: ApplicationContext,
    monkeypatch,
) -> None:
    config = app_context.configuration.model_copy(deep=True)
    config.integrations = IntegrationsConfig(
        prometheus=PrometheusConfig(
            base_url="http://prometheus:9090",
            verify_ssl=False,
            timeout_seconds=10.0,
        )
    )
    config.mcp = config.mcp.model_copy(update={"prometheus_ops_enabled": True})

    monkeypatch.setattr("knowledge_flow_backend.main.load_configuration", lambda: config)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for attr_name in [
        "MonitoringController",
        "MetadataController",
        "ModelController",
        "ContentController",
        "AssetController",
        "WorkspaceStorageController",
        "IngestionController",
        "TagController",
        "VectorSearchController",
        "KPIController",
        "ResourceController",
        "McpFilesystemController",
        "CorpusManagerController",
        "BenchmarkController",
        "TabularController",
        "StatisticController",
        "OpenSearchOpsController",
        "Neo4jController",
        "SchedulerController",
    ]:
        monkeypatch.setattr(main_module, attr_name, lambda *args, **kwargs: None)
    ApplicationContext.reset_instance()

    app = create_app()

    assert any(route.path.startswith(f"{config.app.base_url}/mcp-prometheus-ops") for route in app.routes)

    ApplicationContext.reset_instance()
