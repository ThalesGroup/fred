# Copyright Thales 2025
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


import os
from pathlib import Path

import pytest
from fastapi import FastAPI, Response, WebSocket
from fastapi.testclient import TestClient
from httpx import Headers
from pydantic import ValidationError

from app_backend.common.structures import (
    Configuration,
    ServicesConfig,
    EmbeddedServiceConfig,
)
from app_backend.main import (
    BackendRuntime,
    BackendSpec,
    _backend_config_scope,
    _build_backend_specs,
    _copy_proxy_headers,
    _find_backend,
    _path_matches_prefix,
)


def _runtime(name: str, prefix: str) -> BackendRuntime:
    return BackendRuntime(
        spec=BackendSpec(
            name=name,
            path_prefix=prefix,
            config_file=Path("/tmp"),
            factory=FastAPI,
        ),
        app=FastAPI(),
    )


def test_path_matches_prefix() -> None:
    assert _path_matches_prefix("/agentic/v1", "/agentic/v1")
    assert _path_matches_prefix("/agentic/v1/chat", "/agentic/v1")
    assert not _path_matches_prefix("/agentic/v2/chat", "/agentic/v1")


def test_find_backend_by_prefix() -> None:
    backends = [
        _runtime("agentic", "/agentic/v1"),
        _runtime("knowledge-flow", "/knowledge-flow/v1"),
    ]
    assert _find_backend("/agentic/v1/healthz", backends) == backends[0]
    assert _find_backend("/knowledge-flow/v1/healthz", backends) == backends[1]
    assert _find_backend("/unknown", backends) is None


def test_copy_proxy_headers_filters_hop_headers() -> None:
    response = Response()
    source_headers = Headers(
        {
            "content-type": "application/json",
            "x-request-id": "abc",
            "connection": "keep-alive",
            "content-length": "123",
        }
    )
    _copy_proxy_headers(response, source_headers)
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-request-id"] == "abc"
    assert "connection" not in response.headers
    assert response.headers["content-length"] != "123"


def test_build_backend_specs_uses_configuration_paths() -> None:
    configuration = Configuration(
        services=ServicesConfig(
            control_plane=EmbeddedServiceConfig(
                enabled=True,
                path_prefix="/control-plane/v1",
                config_file="../../control-plane-backend/config/configuration.yaml",
            ),
            agentic=EmbeddedServiceConfig(
                enabled=True,
                path_prefix="/agentic/v1",
                config_file="../../agentic-backend/config/configuration.yaml",
            ),
            knowledge_flow=EmbeddedServiceConfig(
                enabled=False,
                path_prefix="/knowledge-flow/v1",
                config_file="../../knowledge-flow-backend/config/configuration.yaml",
            ),
        ),
    )

    specs = _build_backend_specs(
        configuration,
        Path("/repo/app-backend/config"),
        {
            "control_plane": FastAPI,
            "agentic": FastAPI,
            "knowledge_flow": FastAPI,
        },
    )

    assert len(specs) == 2
    assert specs[0].name == "control-plane"
    assert specs[0].config_file == Path(
        "/repo/control-plane-backend/config/configuration.yaml"
    )
    assert specs[1].name == "agentic"
    assert specs[1].config_file == Path(
        "/repo/agentic-backend/config/configuration.yaml"
    )


def test_configuration_rejects_duplicate_enabled_prefixes() -> None:
    with pytest.raises(ValidationError):
        Configuration(
            services=ServicesConfig(
                control_plane=EmbeddedServiceConfig(
                    enabled=True,
                    path_prefix="/api",
                    config_file="a.yaml",
                ),
                agentic=EmbeddedServiceConfig(
                    enabled=True,
                    path_prefix="/api",
                    config_file="b.yaml",
                ),
                knowledge_flow=EmbeddedServiceConfig(
                    enabled=True,
                    path_prefix="/knowledge-flow/v1",
                    config_file="c.yaml",
                ),
            ),
        )


def test_backend_config_scope_overrides_and_restores_config() -> None:
    os.environ["CONFIG_FILE"] = "/tmp/previous.yaml"

    with _backend_config_scope(Path("/tmp/next.yaml")):
        assert os.environ["CONFIG_FILE"] == "/tmp/next.yaml"

    assert os.environ["CONFIG_FILE"] == "/tmp/previous.yaml"


def test_create_app_proxies_websocket_to_embedded_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_backend.main import create_app

    config = Configuration(
        services=ServicesConfig(
            control_plane=EmbeddedServiceConfig(
                enabled=False,
                path_prefix="/control-plane/v1",
                config_file="control_plane.yaml",
            ),
            agentic=EmbeddedServiceConfig(
                enabled=True,
                path_prefix="/agentic/v1",
                config_file="agentic.yaml",
            ),
            knowledge_flow=EmbeddedServiceConfig(
                enabled=False,
                path_prefix="/knowledge-flow/v1",
                config_file="knowledge_flow.yaml",
            ),
        )
    )

    def _create_fake_agentic_app() -> FastAPI:
        app = FastAPI()
        app.state.service_name = "agentic"

        @app.websocket("/agentic/v1/ws-echo")
        async def _ws_echo(websocket: WebSocket) -> None:
            await websocket.accept()
            payload = await websocket.receive_text()
            await websocket.send_text(
                f"service={websocket.app.state.service_name};payload={payload}"
            )

        return app

    monkeypatch.setattr("app_backend.main.load_configuration", lambda: config)
    monkeypatch.setattr("app_backend.main.get_loaded_config_file_path", lambda: None)
    monkeypatch.setattr("app_backend.main.get_loaded_env_file_path", lambda: None)
    monkeypatch.setattr(
        "app_backend.main._load_backend_factories",
        lambda: {"agentic": _create_fake_agentic_app},
    )

    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/agentic/v1/ws-echo") as websocket:
            websocket.send_text("hello")
            assert websocket.receive_text() == "service=agentic;payload=hello"
