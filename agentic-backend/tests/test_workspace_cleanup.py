import httpx
import pytest
import requests

from agentic_backend.common.kf_workspace_client import (
    KfWorkspaceClient,
    UserStorageResourceInfo,
    WorkspaceRetrievalError,
    WorkspaceUploadError,
)
from agentic_backend.core.chatbot.session_orchestrator import (
    _workspace_file_keys_for_session_cleanup,
)


def _response(payload: object) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "http://example.test/storage/user"),
    )


@pytest.mark.asyncio
async def test_list_user_blobs_returns_typed_resources() -> None:
    class _Client(KfWorkspaceClient):
        async def _request_with_token_refresh(self, *_args, **_kwargs):
            return _response(
                [
                    {
                        "path": "session-1/report.md",
                        "size": 128,
                        "type": "file",
                        "modified": "2026-03-04T09:00:00Z",
                    },
                    {
                        "path": "session-1/",
                        "size": None,
                        "type": "directory",
                        "modified": "2026-03-04T09:00:01Z",
                    },
                    {
                        "path": "session-1/raw.bin",
                        "size": "256",
                        "type": "FilesystemResourceInfo.FILE",
                        "modified": None,
                    },
                ]
            )

    client = object.__new__(_Client)
    blobs = await KfWorkspaceClient.list_user_blobs(client, prefix="session-1/")

    assert [b.path for b in blobs] == [
        "session-1/report.md",
        "session-1/",
        "session-1/raw.bin",
    ]
    assert blobs[0].is_file()
    assert blobs[1].is_directory()
    assert blobs[2].is_file()


@pytest.mark.asyncio
async def test_list_user_blobs_rejects_invalid_payload_shape() -> None:
    class _Client(KfWorkspaceClient):
        async def _request_with_token_refresh(self, *_args, **_kwargs):
            return _response({"unexpected": "object"})

    client = object.__new__(_Client)
    with pytest.raises(ValueError):
        await KfWorkspaceClient.list_user_blobs(client, prefix="session-1/")


def test_workspace_cleanup_ignores_directories_and_deduplicates() -> None:
    resources = [
        UserStorageResourceInfo(
            path="session-1/report.md",
            size=123,
            type="file",
            modified=None,
        ),
        UserStorageResourceInfo(
            path="session-1/",
            size=None,
            type="directory",
            modified=None,
        ),
        UserStorageResourceInfo(
            path="session-1/report.md",
            size=123,
            type="file",
            modified=None,
        ),
        UserStorageResourceInfo(
            path="session-1/slides.pptx",
            size=456,
            type="file",
            modified=None,
        ),
    ]

    assert _workspace_file_keys_for_session_cleanup(resources) == [
        "session-1/report.md",
        "session-1/slides.pptx",
    ]


@pytest.mark.asyncio
async def test_fetch_text_at_path_handles_http_error_without_response() -> None:
    class _Client(KfWorkspaceClient):
        async def _get_file_stream(self, *_args, **_kwargs):
            raise requests.exceptions.HTTPError("network edge case")

    client = object.__new__(_Client)

    with pytest.raises(WorkspaceRetrievalError) as exc_info:
        await KfWorkspaceClient._fetch_text_at_path(
            client, "/storage/user/session-1/report.md"
        )

    assert exc_info.value.status_code is None
    assert "Status: unknown" in str(exc_info.value)


@pytest.mark.asyncio
async def test_upload_blob_maps_httpx_status_error_to_workspace_upload_error() -> None:
    class _Client(KfWorkspaceClient):
        async def _request_with_token_refresh(self, *_args, **_kwargs):
            request = httpx.Request("POST", "http://example.test/storage/user/upload")
            response = httpx.Response(
                413,
                json={"detail": "payload too large"},
                request=request,
            )
            raise httpx.HTTPStatusError(
                "upload failed",
                request=request,
                response=response,
            )

    client = object.__new__(_Client)

    with pytest.raises(WorkspaceUploadError) as exc_info:
        await KfWorkspaceClient._upload_blob(
            client,
            "/storage/user/upload",
            "session-1/report.md",
            b"hello",
            "report.md",
        )

    assert exc_info.value.status_code == 413
    assert "payload too large" in str(exc_info.value)
