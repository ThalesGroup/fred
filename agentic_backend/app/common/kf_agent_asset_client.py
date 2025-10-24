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

import requests

from app.common.kf_base_client import KfBaseClient

if TYPE_CHECKING:
    from app.core.agents.agent_flow import AgentFlow


logger = logging.getLogger(__name__)


class AssetRetrievalError(Exception):
    """Custom exception raised when an agent asset cannot be retrieved."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AssetUploadError(Exception):
    """Custom exception raised when an asset cannot be uploaded."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AssetBlob:
    # Why: single payload with enough context for UI + agent decisions.
    bytes: bytes
    content_type: str
    filename: str
    size: int


@dataclass(frozen=True)
class AssetUploadResult:
    key: str
    file_name: str
    size: int
    document_uid: Optional[str] = None


class KfAgentAssetClient(KfBaseClient):
    """
    Client for fetching user-uploaded assets, inheriting security and retry logic.

    Requires an access_token for all requests.
    """

    def __init__(self, agent: "AgentFlow"):
        # Initialize the base client, specifying the methods we allow (GET and POST)
        super().__init__(
            agent=agent,
            allowed_methods=frozenset({"GET", "POST"}),
        )

    def _get_asset_stream(
        self, agent: str, key: str, access_token: str
    ) -> requests.Response:
        """
        Fetches an asset from the backend. Returns a requests.Response object
        with stream=True set, allowing iteration over content chunks.
        Caller is responsible for closing the response stream.
        Requires access_token for authorization.
        """
        # Endpoint: /agent-assets/{agent}/{key}
        path = f"/agent-assets/{agent}/{key}"

        # Use the base class's authenticated retry mechanism for a GET request.
        r = self._request_with_token_refresh(
            "GET", path, access_token=access_token, stream=True
        )
        r.raise_for_status()  # Raise HTTPError for bad status codes (4xx, 5xx)
        return r

    def fetch_asset_content_text(self, agent: str, key: str, access_token: str) -> str:
        """
        Fetches the complete content of an asset, handles streaming/chunking,
        and returns the decoded content as a string.

        On failure (network, 404, etc.), raises AssetRetrievalError.
        Requires access_token for authorization.
        """
        try:
            # 1. Get the streamed response, passing the required token
            response = self._get_asset_stream(
                agent=agent, key=key, access_token=access_token
            )

            # 2. Read all content from the stream in chunks
            content_bytes = b""
            for chunk in response.iter_content(chunk_size=8192):
                content_bytes += chunk

            # 3. CRITICAL: Close the stream after reading
            response.close()

            # 4. Decode as UTF-8 text (assuming text asset)
            return content_bytes.decode("utf-8")

        # ... (Exception Handling remains the same) ...
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            logger.error(
                f"HTTP error ({status}) reading asset {key}: {e}", exc_info=True
            )

            if status == 404:
                # Specific error for Not Found, very common case
                raise AssetRetrievalError(
                    f"Asset key '{key}' not found (404).", status_code=status
                ) from e

            # General HTTP failure
            raise AssetRetrievalError(
                f"HTTP failure retrieving asset '{key}' (Status: {status}).",
                status_code=status,
            ) from e

        except Exception as e:
            # Catch connection, timeout, decoding, or general I/O errors
            logger.error(f"General error reading asset {key}: {e}", exc_info=True)
            raise AssetRetrievalError(
                f"Failed to read/decode asset '{key}' ({type(e).__name__})."
            ) from e

    def fetch_asset_blob(self, agent: str, key: str, access_token: str) -> AssetBlob:
        """
        Why: Return raw bytes + HTTP metadata. The agent decides if it will:
             - inline a small text preview, or
             - emit an attachment for the UI to download/preview.

        Requires access_token for authorization.
        """
        try:
            resp = self._get_asset_stream(
                agent=agent, key=key, access_token=access_token
            )
            try:
                chunks = []
                total = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        chunks.append(chunk)
                        total += len(chunk)
                content = b"".join(chunks)
            finally:
                # Why: callers must not leak sockets.
                resp.close()

            ctype = resp.headers.get("Content-Type", "application/octet-stream")
            # Try to honor server-provided filename; fallback to 'key'
            disp = resp.headers.get("Content-Disposition", "")
            m = re.search(r"filename\*=UTF-8\'\'([^;]+)", disp) or re.search(
                r'filename="([^"]+)"', disp
            )
            filename = (m.group(1) if m else key) or key

            return AssetBlob(
                bytes=content, content_type=ctype, filename=filename, size=total
            )

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            logger.error(
                f"HTTP error ({status}) reading asset {key}: {e}", exc_info=True
            )
            if status == 404:
                raise AssetRetrievalError(
                    f"Asset key '{key}' not found (404).", status_code=404
                ) from e
            raise AssetRetrievalError(
                f"HTTP failure retrieving asset '{key}' (Status: {status}).",
                status_code=status,
            ) from e
        except Exception as e:
            logger.error(f"General error reading asset {key}: {e}", exc_info=True)
            raise AssetRetrievalError(
                f"Failed to read asset '{key}' ({type(e).__name__})."
            ) from e

    def upload_user_asset_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        access_token: str,  # --- NEW: Required access token
        content_type: Optional[str] = None,
        # NEW ARGUMENT: Explicit ID for the end-user (if the agent knows it)
        user_id_override: Optional[str] = None,
    ) -> AssetUploadResult:
        """
        Uploads a file (generated by the agent) to the user's personal asset storage,
        optionally specifying the target user via user_id_override.

        Requires access_token for authorization.
        """
        # Endpoint: /user-assets/upload
        path = "/user-assets/upload"

        # 1. Define the 'files' payload for multipart/form-data
        files = {
            "file": (filename, file_content, content_type or "application/octet-stream")
        }

        # 2. Define the 'data' payload for form fields
        data = {
            "key": key,
            # CRITICAL CHANGE: Pass the user_id_override as a Form field
            # The controller expects this as a Form(None) parameter for POST
        }
        if user_id_override:
            data["user_id_override"] = user_id_override

        # 3. Perform the POST request
        try:
            r = self._request_with_token_refresh(
                "POST",
                path,
                access_token=access_token,  # Pass the required user token
                files=files,
                data=data,  # This now includes the user_id_override if present
            )

            # Raise HTTPError for bad status codes (4xx, 5xx)
            r.raise_for_status()

            # 4. Parse the successful response
            meta = r.json()

            return AssetUploadResult(
                key=meta.get("key", key),
                file_name=meta.get("file_name", filename),
                size=meta.get("size", 0),
                document_uid=meta.get("document_uid", 0),
            )

        # ... (Exception handling remains the same) ...
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
            raise AssetUploadError(
                f"HTTP failure uploading asset '{key}' (Status: {status}, Detail: {detail}).",
                status_code=status,
            ) from e

        except Exception as e:
            logger.error(f"General error uploading asset {key}: {e}", exc_info=True)
            raise AssetUploadError(
                f"Failed to upload asset '{key}' ({type(e).__name__})."
            ) from e
