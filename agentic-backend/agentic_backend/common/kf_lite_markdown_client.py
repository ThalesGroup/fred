from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from agentic_backend.common.kf_base_client import KfBaseClient


class KfLiteMarkdownClient(KfBaseClient):
    """
    Minimal client for Knowledge Flow's lightweight Markdown extraction endpoint.

    Usage:
        client = KfLiteMarkdownClient(agent=self)
        text = client.extract_markdown(path, max_chars=30000)
    """

    def __init__(self, agent):
        super().__init__(allowed_methods=frozenset({"POST"}), agent=agent)

    def extract_markdown(
        self,
        file_path: Path,
        *,
        max_chars: Optional[int] = 30000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> str:
        """
        Convert a PDF or DOCX to compact Markdown for conversational use.
        Returns the plain text body (format=text).
        """
        # Build options payload compatible with Knowledge Flow endpoint
        options: Dict[str, Any] = {
            "max_chars": max_chars,
            "include_tables": include_tables,
            "add_page_headings": add_page_headings,
            "return_per_page": False,
        }

        # Prepare multipart form-data
        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        with file_path.open("rb") as f:
            files = {
                "file": (file_path.name, f, mime),
            }
            data = {
                "options_json": json.dumps(options),
            }
            r: requests.Response = self._request_with_token_refresh(
                method="POST",
                path="/lite/markdown?format=text",
                files=files,
                data=data,
            )
            r.raise_for_status()
            return r.text or ""

