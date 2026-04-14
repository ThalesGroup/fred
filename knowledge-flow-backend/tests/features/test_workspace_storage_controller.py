from fastapi import APIRouter
from starlette.requests import Request

from knowledge_flow_backend.features.filesystem.workspace_storage_controller import (
    WorkspaceStorageController,
)


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "headers": [(b"host", b"example.test")],
            "query_string": b"",
            "server": ("example.test", 80),
            "client": ("testclient", 50000),
            "root_path": "",
        }
    )


def test_build_download_href_reuses_current_api_prefix() -> None:
    controller = WorkspaceStorageController(APIRouter())

    href = controller._build_download_href(
        _request("/knowledge-flow/v1/storage/user/upload"),
        "storage/user/report.txt",
    )

    assert href == "/knowledge-flow/v1/storage/user/report.txt"


def test_build_download_href_preserves_nested_ingress_prefix() -> None:
    controller = WorkspaceStorageController(APIRouter())

    href = controller._build_download_href(
        _request("/api/platform/knowledge-flow/v1/storage/agent-config/demo-agent/upload"),
        "storage/agent-config/demo-agent/prompt.md",
    )

    assert href == "/api/platform/knowledge-flow/v1/storage/agent-config/demo-agent/prompt.md"
