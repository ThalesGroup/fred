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

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fred_runtime.common.kf_workspace_client import (
    KfWorkspaceClient,
    UserStorageBlob,
    UserStorageResourceInfo,
    UserStorageUploadResult,
    WorkspaceRetrievalError,
    WorkspaceUploadError,
    _coerce_optional_document_uid,
)
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeContext,
    set_runtime_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_httpx_status_error(
    status_code: int, body: bytes = b"error"
) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://test/")
    response = httpx.Response(status_code, content=body, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


def _make_client() -> KfWorkspaceClient:
    set_runtime_context(
        RuntimeContext(RuntimeConfig(knowledge_flow_url="http://test-kf"))
    )
    return KfWorkspaceClient(access_token="tok")


# ---------------------------------------------------------------------------
# _fetch_text_at_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_text_raises_retrieval_error_on_404():
    client = _make_client()
    err = _make_httpx_status_error(404)
    with patch.object(client, "_get_file_stream", side_effect=err):
        with pytest.raises(WorkspaceRetrievalError) as exc_info:
            await client._fetch_text_at_path("/some/path")
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_fetch_text_raises_retrieval_error_on_500():
    client = _make_client()
    err = _make_httpx_status_error(500)
    with patch.object(client, "_get_file_stream", side_effect=err):
        with pytest.raises(WorkspaceRetrievalError) as exc_info:
            await client._fetch_text_at_path("/some/path")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_fetch_text_raises_retrieval_error_on_generic_exception():
    client = _make_client()
    with patch.object(
        client, "_get_file_stream", side_effect=ConnectionError("timeout")
    ):
        with pytest.raises(WorkspaceRetrievalError) as exc_info:
            await client._fetch_text_at_path("/some/path")
    assert exc_info.value.status_code is None


@pytest.mark.asyncio
async def test_fetch_text_returns_decoded_string():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.aiter_bytes = MagicMock(
        return_value=aiter_from([b"hello ", b"world"])
    )
    mock_response.aclose = AsyncMock()
    with patch.object(client, "_get_file_stream", return_value=mock_response):
        result = await client._fetch_text_at_path("/some/path")
    assert result == "hello world"


# ---------------------------------------------------------------------------
# _fetch_blob_at_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_blob_raises_retrieval_error_on_404():
    client = _make_client()
    err = _make_httpx_status_error(404)
    with patch.object(client, "_get_file_stream", side_effect=err):
        with pytest.raises(WorkspaceRetrievalError) as exc_info:
            await client._fetch_blob_at_path("/some/path")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_blob_returns_blob_on_success():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.aiter_bytes = MagicMock(return_value=aiter_from([b"\x00\x01\x02"]))
    mock_response.aclose = AsyncMock()
    mock_response.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="test.bin"',
    }
    with patch.object(client, "_get_file_stream", return_value=mock_response):
        blob = await client._fetch_blob_at_path("/some/path")
    assert isinstance(blob, UserStorageBlob)
    assert blob.bytes == b"\x00\x01\x02"
    assert blob.size == 3
    assert blob.filename == "test.bin"


# ---------------------------------------------------------------------------
# _upload_blob
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_blob_raises_upload_error_on_http_error():
    client = _make_client()
    request = httpx.Request("POST", "http://test/upload")
    response = httpx.Response(
        413,
        content=b'{"detail": "Too large"}',
        request=request,
        headers={"content-type": "application/json"},
    )
    err = httpx.HTTPStatusError("413", request=request, response=response)
    with patch.object(client, "_request_with_token_refresh", side_effect=err):
        with pytest.raises(WorkspaceUploadError) as exc_info:
            await client._upload_blob("/upload", "key", b"data", "file.bin")
    assert exc_info.value.status_code == 413
    assert "Too large" in str(exc_info.value)


@pytest.mark.asyncio
async def test_upload_blob_raises_upload_error_on_generic_exception():
    client = _make_client()
    with patch.object(
        client, "_request_with_token_refresh", side_effect=OSError("disk full")
    ):
        with pytest.raises(WorkspaceUploadError) as exc_info:
            await client._upload_blob("/upload", "key", b"data", "file.bin")
    assert exc_info.value.status_code is None


@pytest.mark.asyncio
async def test_upload_blob_returns_result_on_success():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "key": "stored/key",
            "file_name": "file.bin",
            "size": 4,
            "document_uid": "uid-123",
            "download_url": "http://example.com/dl",
        }
    )
    with patch.object(
        client, "_request_with_token_refresh", return_value=mock_response
    ):
        result = await client._upload_blob("/upload", "key", b"data", "file.bin")
    assert isinstance(result, UserStorageUploadResult)
    assert result.key == "stored/key"
    assert result.document_uid == "uid-123"


# ---------------------------------------------------------------------------
# list_user_blobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_user_blobs_returns_file_entries():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value=[
            {"path": "/a/b.txt", "size": 100, "type": "file", "modified": "2026-01-01"},
            {"path": "/a/dir", "size": None, "type": "directory", "modified": None},
        ]
    )
    with patch.object(
        client, "_request_with_token_refresh", return_value=mock_response
    ):
        entries = await client.list_user_blobs()
    assert len(entries) == 2
    assert entries[0].is_file()
    assert entries[1].is_directory()


@pytest.mark.asyncio
async def test_list_user_blobs_raises_on_non_list_response():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"error": "bad"})
    with patch.object(
        client, "_request_with_token_refresh", return_value=mock_response
    ):
        with pytest.raises(ValueError, match="expected a list"):
            await client.list_user_blobs()


# ---------------------------------------------------------------------------
# Unified team-rooted /fs path API (FILES-04)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fs_download_blob_uses_fs_download_route():
    client = _make_client()
    blob = UserStorageBlob(b"x", "application/octet-stream", "x", 1)
    with patch.object(client, "_fetch_blob_at_path", return_value=blob) as m:
        result = await client.fs_download_blob("teams/acme/shared/templates/deck.pptx")
    assert result is blob
    m.assert_awaited_once_with("/fs/download/teams/acme/shared/templates/deck.pptx", None)


@pytest.mark.asyncio
async def test_fs_read_text_decodes_downloaded_bytes():
    client = _make_client()
    blob = UserStorageBlob("héllo".encode("utf-8"), "text/plain", "x.md", 6)
    with patch.object(client, "fs_download_blob", return_value=blob):
        text = await client.fs_read_text("teams/acme/shared/notes.md")
    assert text == "héllo"


@pytest.mark.asyncio
async def test_fs_upload_uses_fs_upload_route():
    client = _make_client()
    expected = UserStorageUploadResult(key="k", file_name="d.pptx", size=4)
    with patch.object(client, "_upload_blob", return_value=expected) as m:
        result = await client.fs_upload(
            "teams/acme/users/u-1/outputs/d.pptx", b"data", "d.pptx", "application/octet-stream"
        )
    assert result is expected
    m.assert_awaited_once_with(
        "/fs/upload/teams/acme/users/u-1/outputs/d.pptx",
        "teams/acme/users/u-1/outputs/d.pptx",
        b"data",
        "d.pptx",
        "application/octet-stream",
    )


@pytest.mark.asyncio
async def test_fs_delete_calls_delete_route():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch.object(client, "_request_with_token_refresh", return_value=mock_response) as m:
        await client.fs_delete("teams/acme/shared/x.txt")
    args, _kwargs = m.call_args
    assert args[0] == "DELETE"
    assert args[1] == "/fs/delete/teams/acme/shared/x.txt"


@pytest.mark.asyncio
async def test_fs_list_parses_entries_and_passes_path():
    client = _make_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value=[{"path": "deck.pptx", "size": 10, "type": "file", "modified": None}]
    )
    with patch.object(client, "_request_with_token_refresh", return_value=mock_response) as m:
        entries = await client.fs_list("teams/acme/shared")
    assert len(entries) == 1
    assert entries[0].is_file()
    args, kwargs = m.call_args
    assert args[0] == "GET"
    assert args[1] == "/fs/list"
    assert kwargs["params"] == {"path": "teams/acme/shared"}


# ---------------------------------------------------------------------------
# _normalize_resource_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("file", "file"),
        ("FileSystemResourceInfo.File", "file"),
        ("directory", "directory"),
        ("dir", "directory"),
        ("FileSystemResourceInfo.Directory", "directory"),
        ("unknown_type", "unknown"),
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_normalize_resource_type(value: object, expected: str):
    assert KfWorkspaceClient._normalize_resource_type(value) == expected


# ---------------------------------------------------------------------------
# _parse_user_storage_resource
# ---------------------------------------------------------------------------


def test_parse_user_storage_resource_returns_none_for_non_dict():
    assert KfWorkspaceClient._parse_user_storage_resource("not a dict") is None
    assert KfWorkspaceClient._parse_user_storage_resource(None) is None


def test_parse_user_storage_resource_returns_none_for_missing_path():
    assert KfWorkspaceClient._parse_user_storage_resource({"size": 1}) is None


def test_parse_user_storage_resource_parses_full_entry():
    result = KfWorkspaceClient._parse_user_storage_resource(
        {
            "path": "/foo/bar.txt",
            "size": "1024",
            "type": "file",
            "modified": "2026-01-01T00:00:00Z",
        }
    )
    assert result is not None
    assert isinstance(result, UserStorageResourceInfo)
    assert result.path == "/foo/bar.txt"
    assert result.size == 1024
    assert result.is_file()


# ---------------------------------------------------------------------------
# _coerce_optional_document_uid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (True, None),
        (False, None),
        ("", None),
        ("0", None),
        ("  ", None),
        ("uid-abc", "uid-abc"),
        (0, None),
        (0.0, None),
        (42, "42"),
    ],
)
def test_coerce_optional_document_uid(value: object, expected: str | None):
    assert _coerce_optional_document_uid(value) == expected


# ---------------------------------------------------------------------------
# Async iterator helper
# ---------------------------------------------------------------------------


async def aiter_from(items: list[bytes]):
    for item in items:
        yield item
