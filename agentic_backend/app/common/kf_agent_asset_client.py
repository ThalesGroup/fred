# app/core/http/asset_client.py (Derived from base client)

from __future__ import annotations

import logging
from typing import Optional

import requests

from app.common.kf_base_client import KfBaseClient

logger = logging.getLogger(__name__)


class AssetRetrievalError(Exception):
    """Custom exception raised when an agent asset cannot be retrieved."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class KfAgentAssetClient(KfBaseClient):
    """
    Client for fetching user-uploaded assets, inheriting security and retry logic.
    """

    def __init__(self):
        # Initialize the base client, specifying the methods we allow (GET only)
        super().__init__(allowed_methods=frozenset({"GET"}))

    def _get_asset_stream(self, agent: str, key: str) -> requests.Response:
        """
        Fetches an asset from the backend. Returns a requests.Response object
        with stream=True set, allowing iteration over content chunks.
        Caller is responsible for closing the response stream.
        """
        # Endpoint: /agent-assets/{agent}/{key}
        path = f"/agent-assets/{agent}/{key}"

        # Use the base class's authenticated retry mechanism for a GET request.
        # Setting stream=True is required for downloading file content.
        r = self._request_with_auth_retry("GET", path, stream=True)
        r.raise_for_status()  # Raise HTTPError for bad status codes (4xx, 5xx)
        return r

    def fetch_asset_content_text(self, agent: str, key: str) -> str:
        """
        Fetches the complete content of an asset, handles streaming/chunking,
        and returns the decoded content as a string.

        On failure (network, 404, etc.), raises AssetRetrievalError.
        """
        try:
            # 1. Get the streamed response
            response = self._get_asset_stream(agent=agent, key=key)

            # 2. Read all content from the stream in chunks
            content_bytes = b""
            for chunk in response.iter_content(chunk_size=8192):
                content_bytes += chunk

            # 3. CRITICAL: Close the stream after reading
            response.close()

            # 4. Decode as UTF-8 text (assuming text asset)
            return content_bytes.decode("utf-8")

        # --- Exception Handling ---

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
