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

import io
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

from agentic_backend.common.kf_base_client import KfBaseClient


class KfFastTextClient(KfBaseClient):
    """
    Minimal client for Knowledge Flow's lightweight Markdown extraction endpoint.
    Usage:
        # Agent mode (unchanged):
        client = KfFastTextClient(agent=my_agent)

        # Session mode (conversation/controller):
        client = KfFastTextClient(access_token=session_access_token, refresh_user_access_token=my_refresh_fn)
    """

    def __init__(
        self,
        agent=None,
        *,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        super().__init__(
            allowed_methods=frozenset({"POST"}),
            agent=agent,
            access_token=access_token,
            refresh_user_access_token=refresh_user_access_token,
        )

    def extract_text_from_bytes(
        self,
        *,
        filename: str,
        content: bytes,
        mime: Optional[str] = None,
        max_chars: Optional[int] = 30000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> str:
        """
        Fred rationale: identical security (Bearer user token), but avoids local temp files.
        Sends a multipart/form-data with an in-memory file-like object.
        """
        options: Dict[str, Any] = {
            "max_chars": max_chars,
            "include_tables": include_tables,
            "add_page_headings": add_page_headings,
            "return_per_page": False,
        }
        mime = mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {"file": (filename, io.BytesIO(content), mime)}
        data = {"options_json": json.dumps(options)}
        r: requests.Response = self._request_with_token_refresh(
            method="POST",
            path="/fast/text?format=text",
            files=files,
            data=data,
        )
        r.raise_for_status()
        return r.text or ""

    def ingest_text_from_bytes(
        self,
        *,
        filename: str,
        content: bytes,
        session_id: Optional[str] = None,
        scope: str = "session",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Fast ingest path: use the fast extractor and store vectors with scoping metadata.
        Returns the backend payload (document_uid, chunks, etc.).
        """
        options_json = json.dumps(options or {})
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {"file": (filename, io.BytesIO(content), mime)}
        data = {
            "options_json": options_json,
            "session_id": session_id or "",
            "scope": scope,
        }
        r: requests.Response = self._request_with_token_refresh(
            method="POST",
            path="/fast/ingest",
            files=files,
            data=data,
        )
        r.raise_for_status()
        return r.json()

    def delete_ingested_vectors(self, document_uid: str) -> None:
        """
        Delete vectors created via the fast ingest path.
        """
        r: requests.Response = self._request_with_token_refresh(
            method="DELETE",
            path=f"/fast/ingest/{document_uid}",
        )
        r.raise_for_status()

    def extract_text(
        self,
        file_path: Path,
        *,
        max_chars: Optional[int] = 30000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> str:
        options: Dict[str, Any] = {
            "max_chars": max_chars,
            "include_tables": include_tables,
            "add_page_headings": add_page_headings,
            "return_per_page": False,
        }

        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, mime)}
            data = {"options_json": json.dumps(options)}
            r: requests.Response = self._request_with_token_refresh(
                method="POST",
                path="/fast/text?format=text",
                files=files,
                data=data,
            )
            r.raise_for_status()
            return r.text or ""
