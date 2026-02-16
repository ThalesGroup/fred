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
from typing import TYPE_CHECKING, BinaryIO, Optional

import httpx
import requests

from agentic_backend.common.kf_base_client import KfBaseClient

if TYPE_CHECKING:
    from agentic_backend.core.agents.agent_flow import AgentFlow


logger = logging.getLogger(__name__)


class WorkspaceRetrievalError(Exception):
    """Raised when an agent configuration file cannot be retrieved."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class WorkspaceUploadError(Exception):
    """Raised when an asset cannot be uploaded."""

    def __init__(self, message: str, status_code: Optional[int] = None):
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
    document_uid: Optional[str] = None
    download_url: Optional[str] = None


class KfWorkspaceClient(KfBaseClient):
    """
    Workspace client for non-corpus files.

    Three clear use-cases (and matching dedicated methods):
    1) User exchange (end-user ↔ agent): `fetch_user_*`, `upload_user_file`, `delete_user_file`.
    2) Agent configuration (admin-managed, agent-read): `fetch_agent_config_*`, `upload_agent_config_file`, `delete_agent_config_file`.
    3) Agent per-user notes (agent-private, per end-user): `fetch_agent_user_*`, `upload_agent_user_file`, `delete_agent_user_file`.
    """

    def __init__(self, agent: "AgentFlow"):
        super().__init__(
            agent=agent, allowed_methods=frozenset({"GET", "POST", "DELETE"})
        )

    # ---------------- Path helpers (dedicated) ----------------
    @staticmethod
    def _path_user_download(key: str) -> str:
        return f"/storage/user/{key}"

    @staticmethod
    def _path_user_upload() -> str:
        return "/storage/user/upload"

    @staticmethod
    def _path_agent_config_download(agent_id: str, key: str) -> str:
        return f"/storage/agent-config/{agent_id}/{key}"

    @staticmethod
    def _path_agent_config_upload(agent_id: str) -> str:
        return f"/storage/agent-config/{agent_id}/upload"

    @staticmethod
    def _path_agent_user_download(agent_id: str, target_user_id: str, key: str) -> str:
        return f"/storage/agent-user/{agent_id}/{target_user_id}/{key}"

    @staticmethod
    def _path_agent_user_upload(agent_id: str, target_user_id: str) -> str:
        return f"/storage/agent-user/{agent_id}/{target_user_id}/upload"

    # ---------------- Core operations ----------------
    async def _get_file_stream(self, path: str, access_token: str) -> httpx.Response:
        r = await self._request_with_token_refresh(
            "GET",
            path,
            phase_name="kf_workspace_fetch_stream",
            access_token=access_token,
            stream=True,
        )
        r.raise_for_status()
        return r

    async def _fetch_text_at_path(self, path: str, access_token: str) -> str:
        """Fetch the complete text content of a user file."""
        try:
            response = await self._get_file_stream(path, access_token)

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
            await response.aclose()
            return bytes(content).decode("utf-8")

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            logger.error(
                f"HTTP error ({status}) reading asset at {path}: {e}", exc_info=True
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
            logger.error(f"General error reading asset {path}: {e}", exc_info=True)
            raise WorkspaceRetrievalError(
                f"Failed to read/decode asset '{path}' ({type(e).__name__})."
            ) from e

    # -------------- Public dedicated methods --------------
    async def fetch_user_text(self, key: str, access_token: str) -> str:
        """Lire un fichier d'échange utilisateur → agent (ex: rapport généré) en texte clair."""
        return await self._fetch_text_at_path(
            self._path_user_download(key), access_token
        )

    async def fetch_agent_config_text(
        self, key: str, access_token: str, agent_id: str
    ) -> str:
        """Lire un fichier de configuration d'agent (ex: template, prompt) en texte clair."""
        return await self._fetch_text_at_path(
            self._path_agent_config_download(agent_id, key), access_token
        )

    async def fetch_agent_user_text(
        self, key: str, access_token: str, agent_id: str, target_user_id: str
    ) -> str:
        """Lire une note mémo privée d'un agent pour un utilisateur donné (agent-only)."""
        return await self._fetch_text_at_path(
            self._path_agent_user_download(agent_id, target_user_id, key), access_token
        )

    async def _fetch_blob_at_path(
        self, path: str, access_token: str
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

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            logger.error(
                f"HTTP error ({status}) reading asset {path}: {e}", exc_info=True
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
            logger.error(f"General error reading asset {path}: {e}", exc_info=True)
            raise WorkspaceRetrievalError(
                f"Failed to read asset '{path}' ({type(e).__name__})."
            ) from e

    async def fetch_user_blob(self, key: str, access_token: str) -> UserStorageBlob:
        """Récupérer un fichier d'échange utilisateur → agent (binaire + métadonnées)."""
        return await self._fetch_blob_at_path(
            self._path_user_download(key), access_token
        )

    async def fetch_agent_config_blob(
        self, key: str, access_token: str, agent_id: str
    ) -> UserStorageBlob:
        """Récupérer un fichier de configuration d'agent (binaire + métadonnées)."""
        return await self._fetch_blob_at_path(
            self._path_agent_config_download(agent_id, key), access_token
        )

    async def fetch_agent_user_blob(
        self, key: str, access_token: str, agent_id: str, target_user_id: str
    ) -> UserStorageBlob:
        """Récupérer une note privée agent↔utilisateur (binaire + métadonnées)."""
        return await self._fetch_blob_at_path(
            self._path_agent_user_download(agent_id, target_user_id, key), access_token
        )

    # ---------------- Uploads ----------------
    async def _upload_blob(
        self,
        path: str,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        content_type: Optional[str] = None,
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
                document_uid=meta.get("document_uid", 0),
                download_url=meta.get("download_url"),
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            detail = (
                e.response.json().get("detail", "No detail provided")
                if e.response.content
                else e.response.reason
            )
            logger.error(
                f"HTTP error ({status}) uploading asset {key}: {detail}", exc_info=True
            )
            raise WorkspaceUploadError(
                f"HTTP failure uploading asset '{key}' (Status: {status}, Detail: {detail}).",
                status_code=status,
            ) from e
        except Exception as e:
            logger.error(f"General error uploading asset {key}: {e}", exc_info=True)
            raise WorkspaceUploadError(
                f"Failed to upload asset '{key}' ({type(e).__name__})."
            ) from e

    async def upload_user_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        content_type: Optional[str] = None,
    ) -> UserStorageUploadResult:
        """Déposer un fichier pour un utilisateur (ex: rapport à télécharger)."""
        path = self._path_user_upload()
        return await self._upload_blob(path, key, file_content, filename, content_type)

    async def upload_agent_config_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        agent_id: str,
        content_type: Optional[str] = None,
    ) -> UserStorageUploadResult:
        """Déposer un fichier de configuration d'agent (ex: template, prompt)."""
        path = self._path_agent_config_upload(agent_id)
        return await self._upload_blob(path, key, file_content, filename, content_type)

    async def upload_agent_user_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        agent_id: str,
        target_user_id: str,
        content_type: Optional[str] = None,
    ) -> UserStorageUploadResult:
        """Déposer une note privée pour un utilisateur spécifique (carnet de l'agent)."""
        path = self._path_agent_user_upload(agent_id, target_user_id)
        return await self._upload_blob(path, key, file_content, filename, content_type)

    async def delete_user_blob(self, key: str, access_token: str) -> None:
        """Supprimer un fichier côté espace utilisateur."""
        path = self._path_user_download(key)
        r = await self._request_with_token_refresh(
            "DELETE",
            path,
            phase_name="kf_workspace_delete_user",
            access_token=access_token,
        )
        r.raise_for_status()

    async def delete_agent_config_blob(
        self, key: str, access_token: str, agent_id: str
    ) -> None:
        """Supprimer un fichier de configuration d'agent."""
        path = self._path_agent_config_download(agent_id, key)
        r = await self._request_with_token_refresh(
            "DELETE",
            path,
            phase_name="kf_workspace_delete_agent_config",
            access_token=access_token,
        )
        r.raise_for_status()

    async def delete_agent_user_blob(
        self, key: str, access_token: str, agent_id: str, target_user_id: str
    ) -> None:
        """Supprimer une note privée agent↔utilisateur."""
        path = self._path_agent_user_download(agent_id, target_user_id, key)
        r = await self._request_with_token_refresh(
            "DELETE",
            path,
            phase_name="kf_workspace_delete_agent_user",
            access_token=access_token,
        )
        r.raise_for_status()
