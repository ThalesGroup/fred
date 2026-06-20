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

import logging
import re
from dataclasses import dataclass
from typing import BinaryIO, Callable

import httpx

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext

logger = logging.getLogger(__name__)


class WorkspaceRetrievalError(Exception):
    """Raised when an agent configuration file cannot be retrieved."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class WorkspaceUploadError(Exception):
    """Raised when an asset cannot be uploaded."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class UserStorageBlob:
    bytes: bytes
    content_type: str
    filename: str
    size: int


@dataclass(frozen=True)
class UserStorageUploadResult:
    key: str
    file_name: str
    size: int
    document_uid: str | None = None
    download_url: str | None = None


@dataclass(frozen=True)
class UserStorageResourceInfo:
    """
    One entry returned by workspace listing endpoints.

    `type` is normalized to either:
    - `file`
    - `directory`
    - `unknown`
    """

    path: str
    size: int | None
    type: str
    modified: str | None

    def is_file(self) -> bool:
        return self.type == "file"

    def is_directory(self) -> bool:
        return self.type == "directory"


class KfWorkspaceClient(KfBaseClient):
    """
    Workspace client for non-corpus files.

    Three clear use-cases (and matching dedicated methods):
    1) User exchange (end-user ↔ agent): `fetch_user_*`, `upload_user_file`, `delete_user_file`.
    2) Agent configuration (admin-managed, agent-read): `fetch_agent_config_*`, `upload_agent_config_file`, `delete_agent_config_file`.
    3) Agent per-user notes (agent-private, per end-user): `fetch_agent_user_*`, `upload_agent_user_file`, `delete_agent_user_file`.
    """

    def __init__(
        self,
        agent: KnowledgeFlowAgentContext | None = None,
        *,
        access_token: str | None = None,
        refresh_user_access_token: Callable[[], str] | None = None,
    ):
        """
        Why: keep workspace access bound to the caller's runtime identity.
        How: provide an agent context or explicit access token/refresh callback.
        Example:
            >>> client = KfWorkspaceClient(agent=agent_ctx)
        """
        super().__init__(
            agent=agent,
            access_token=access_token,
            refresh_user_access_token=refresh_user_access_token,
            allowed_methods=frozenset({"GET", "POST", "DELETE"}),
        )

    # ---------------- Core operations ----------------
    async def _get_file_stream(
        self, path: str, access_token: str | None = None
    ) -> httpx.Response:
        r = await self._request_with_token_refresh(
            "GET",
            path,
            phase_name="kf_workspace_fetch_stream",
            access_token=access_token,
            stream=True,
        )
        r.raise_for_status()
        return r

    async def _fetch_text_at_path(
        self, path: str, access_token: str | None = None
    ) -> str:
        """Fetch the complete text content of a user file."""
        try:
            response = await self._get_file_stream(path, access_token)

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
            await response.aclose()
            return bytes(content).decode("utf-8")

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(
                "HTTP error (%s) reading asset at %s: %s",
                status,
                path,
                e,
                exc_info=True,
            )
            if status == 404:
                raise WorkspaceRetrievalError(
                    f"Asset path '{path}' not found (404).", status_code=status
                ) from e
            raise WorkspaceRetrievalError(
                f"HTTP failure retrieving asset '{path}' (Status: {status}).",
                status_code=status,
            ) from e
        except Exception as e:
            logger.error("General error reading asset %s: %s", path, e, exc_info=True)
            raise WorkspaceRetrievalError(
                f"Failed to read/decode asset '{path}' ({type(e).__name__})."
            ) from e

    async def _fetch_blob_at_path(
        self, path: str, access_token: str | None = None
    ) -> UserStorageBlob:
        """
        Why: Return raw bytes + HTTP metadata. The agent decides if it will:
             - inline a small text preview, or
             - emit an attachment for the UI to download/preview.

        Requires access_token for authorization.
        """
        try:
            resp = await self._get_file_stream(path, access_token)
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes():
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
            content = b"".join(chunks)
            await resp.aclose()

            ctype = resp.headers.get("Content-Type", "application/octet-stream")
            disp = resp.headers.get("Content-Disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)", disp) or re.search(
                r'filename="([^"]+)"', disp
            )
            filename = (m.group(1) if m else path.split("/")[-1]) or path

            return UserStorageBlob(
                bytes=content, content_type=ctype, filename=filename, size=total
            )

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(
                "HTTP error (%s) reading asset %s: %s",
                status,
                path,
                e,
                exc_info=True,
            )
            if status == 404:
                raise WorkspaceRetrievalError(
                    f"Asset path '{path}' not found (404).", status_code=404
                ) from e
            raise WorkspaceRetrievalError(
                f"HTTP failure retrieving asset '{path}' (Status: {status}).",
                status_code=status,
            ) from e
        except Exception as e:
            logger.error("General error reading asset %s: %s", path, e, exc_info=True)
            raise WorkspaceRetrievalError(
                f"Failed to read asset '{path}' ({type(e).__name__})."
            ) from e

    # ---------------- Uploads ----------------
    async def _upload_blob(
        self,
        path: str,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        content_type: str | None = None,
    ) -> UserStorageUploadResult:
        logger.info(
            "UPLOADING_ASSET: Attempting to upload asset to %s key=%s", path, key
        )
        files = {
            "file": (filename, file_content, content_type or "application/octet-stream")
        }
        data = {"key": key}
        try:
            r = await self._request_with_token_refresh(
                "POST",
                path,
                phase_name="kf_workspace_upload",
                files=files,
                data=data,
            )
            r.raise_for_status()
            meta = r.json()
            return UserStorageUploadResult(
                key=meta.get("key", key),
                file_name=meta.get("file_name", filename),
                size=meta.get("size", 0),
                document_uid=_coerce_optional_document_uid(meta.get("document_uid")),
                download_url=meta.get("download_url"),
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            detail = (
                e.response.json().get("detail", "No detail provided")
                if e.response.content
                else e.response.reason_phrase
            )
            logger.error(
                "HTTP error (%s) uploading asset %s: %s",
                status,
                key,
                detail,
                exc_info=True,
            )
            raise WorkspaceUploadError(
                f"HTTP failure uploading asset '{key}' (Status: {status}, Detail: {detail}).",
                status_code=status,
            ) from e
        except Exception as e:
            logger.error("General error uploading asset %s: %s", key, e, exc_info=True)
            raise WorkspaceUploadError(
                f"Failed to upload asset '{key}' ({type(e).__name__})."
            ) from e

    # ----------------------------------------------------------------- #
    # Unified team-rooted /fs path API (FILES-04)
    #
    # These methods address files by a single team-rooted virtual path
    # (e.g. "teams/{team}/shared/templates/deck.pptx"). The path carries the
    # team, and Knowledge Flow authorizes it via ReBAC. Building that path from
    # the verified session context (team/user) is the caller's job, never this
    # client's — it only forwards the path.
    # ----------------------------------------------------------------- #
    @staticmethod
    def _fs_path(verb: str, path: str) -> str:
        return f"/fs/{verb}/{path.lstrip('/')}"

    async def fs_download_blob(self, path: str, access_token: str | None = None) -> UserStorageBlob:
        """Download one team-rooted file (binary content + metadata) via GET /fs/download/{path}."""
        return await self._fetch_blob_at_path(self._fs_path("download", path), access_token)

    async def fs_read_text(self, path: str, access_token: str | None = None) -> str:
        """
        Read one team-rooted file as raw UTF-8 text.

        Uses the binary download route (not /fs/cat, which renders numbered excerpts) so the
        content round-trips byte-for-byte before decoding.
        """
        blob = await self.fs_download_blob(path, access_token)
        return blob.bytes.decode("utf-8")

    async def fs_upload(
        self,
        path: str,
        file_content: bytes | BinaryIO,
        filename: str,
        content_type: str | None = None,
    ) -> UserStorageUploadResult:
        """Upload one team-rooted file via POST /fs/upload/{path} (multipart)."""
        return await self._upload_blob(self._fs_path("upload", path), path, file_content, filename, content_type)

    async def fs_delete(self, path: str, access_token: str | None = None) -> None:
        """Delete one team-rooted file via DELETE /fs/delete/{path}."""
        r = await self._request_with_token_refresh(
            "DELETE",
            self._fs_path("delete", path),
            phase_name="kf_fs_delete",
            access_token=access_token,
        )
        r.raise_for_status()

    async def fs_list(self, path: str = "/", access_token: str | None = None) -> list[UserStorageResourceInfo]:
        """List one team-rooted directory via GET /fs/list?path=..."""
        r = await self._request_with_token_refresh(
            "GET",
            "/fs/list",
            phase_name="kf_fs_list",
            params={"path": path},
            access_token=access_token,
        )
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list):
            raise ValueError("Invalid /fs/list response: expected a list.")
        items: list[UserStorageResourceInfo] = []
        for raw in payload:
            parsed = self._parse_user_storage_resource(raw)
            if parsed is not None:
                items.append(parsed)
        return items

    @staticmethod
    def _normalize_resource_type(value: object) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "unknown"
        if raw in {"file", "filesystemresourceinfo.file"} or raw.endswith(".file"):
            return "file"
        if raw in {
            "directory",
            "dir",
            "filesystemresourceinfo.directory",
        } or raw.endswith(".directory"):
            return "directory"
        return "unknown"

    @classmethod
    def _parse_user_storage_resource(
        cls, payload: object
    ) -> UserStorageResourceInfo | None:
        if not isinstance(payload, dict):
            return None

        path = str(payload.get("path") or "").strip()
        if not path:
            return None

        size_value = payload.get("size")
        size: int | None = None
        if isinstance(size_value, int):
            size = size_value
        elif isinstance(size_value, float):
            size = int(size_value)
        elif isinstance(size_value, str):
            try:
                size = int(size_value)
            except ValueError:
                size = None

        modified_value = payload.get("modified")
        modified = str(modified_value) if modified_value is not None else None

        return UserStorageResourceInfo(
            path=path,
            size=size,
            type=cls._normalize_resource_type(payload.get("type")),
            modified=modified,
        )


def _coerce_optional_document_uid(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned and cleaned != "0" else None
    if isinstance(value, int | float):
        return None if value == 0 else str(value)
    return str(value)
