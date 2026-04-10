import httpx
import pytest

from agentic_backend.common.kf_workspace_client import (
    KfWorkspaceClient,
    UserStorageResourceInfo,
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
