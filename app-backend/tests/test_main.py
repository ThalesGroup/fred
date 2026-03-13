from pathlib import Path

import pytest
from fastapi import FastAPI, Response
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
