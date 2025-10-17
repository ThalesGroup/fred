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

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)


# --- Response Models ---
class DocumentContent(BaseModel):
    """
    Model representing a document's content and metadata.
    """

    uid: str
    file_name: str
    title: str = ""
    content: Any = None
    has_binary_content: bool = False
    content_type: str = "application/octet-stream"
    file_url: str = ""
    modified: str = ""
    metadata: Dict[str, Any] = {}


class MarkdownContentResponse(BaseModel):
    content: str


def parse_range_header(range_str: Optional[str]) -> Optional[tuple[int | None, int | None]]:
    """
    Parse 'Range: bytes=START-END' (inclusive). Returns (start, end) where either can be None.

    Supported:
      - bytes=0-499      -> (0, 499)
      - bytes=500-       -> (500, None)
      - bytes=-500       -> (None, -500)  # suffix: last 500 bytes
    Multiple ranges are NOT supported (we’ll 416 on those for simplicity).
    """
    if not range_str or not range_str.startswith("bytes="):
        return None
    import re

    m = re.match(r"bytes=(\d*)-(\d*)$", range_str.strip())
    if not m:
        return None
    start_s, end_s = m.groups()
    start = int(start_s) if start_s else None
    end = int(end_s) if end_s else None
    return start, end


class ContentController:
    """
    Controller responsible for serving document content and previews.

    Current Responsibilities:
    --------------------------
    This controller exposes read-only endpoints to access document content:
    - Serve raw binary files uploaded during ingestion
    - Serve full Markdown previews rendered from extracted/processed content

    It bridges the backend storage layer with frontend-facing APIs that:
    - Render documents in the UI (markdown preview)
    - Allow download of original files (raw content)

    Design Note:
    ------------
    In the current implementation, this controller operates in a **passive role**:
    it only retrieves content, with no ingestion or transformation logic.

    In future iterations, the platform may introduce:
    - A separate **Content Upload API** (to decouple ingestion and upload)
    - Access control or document-level authorization
    - Support for streaming large files or paginated markdown rendering

    Developers should treat this controller as **stable**, with low coupling to
    the processing pipeline. It is safe to extend for new access-related use cases.

    Endpoints:
    ----------
    - `GET /markdown/{document_uid}`: returns the full markdown preview of a document
    - `GET /raw_content/{document_uid}`: streams the original uploaded file for download

    Dependencies:
    -------------
    - `ContentService`: abstracts retrieval from storage backend (e.g., filesystem, MinIO)
    """

    def __init__(self, router: APIRouter):
        """
        Initialize the controller with a FastAPI router and content service.
        """
        from app.features.content.content_service import ContentService

        self.service = ContentService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        """
        Register all content-related routes with the provided router.
        """

        @router.get(
            "/markdown/{document_uid}",
            tags=["Content"],
            summary="Get markdown preview of a processed document",
            description="""
        Returns the full Markdown preview of a document that has been successfully ingested and processed (either via push or pull mode).

        This preview is only available if the document passed through the chunking or parsing pipeline that generated Markdown content.

        ### When this works:
        - The document was uploaded (push) or discovered and processed (pull)
        - A Markdown preview was created during ingestion

        ### When this fails:
        - The document has not been processed yet
        - The ingestion failed before preview generation

        """,
            response_model=MarkdownContentResponse,
        )
        async def get_markdown_preview(document_uid: str, user: KeycloakUser = Depends(get_current_user)):
            """
            Endpoint to retrieve a complete document including its content.
            """
            try:
                logger.info(f"Retrieving full document: {document_uid}")
                content = await self.service.get_markdown_preview(user, document_uid)
                return {"content": content}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.get(
            "/markdown/{document_uid}/media/{media_id}",
            tags=["Content"],
            summary="Download an embedded media asset from a processed document",
            description="""
        Fetches an embedded media resource (e.g., image or attachment) that was extracted during the ingestion of a processed document.

        This is only available for documents that had media assets linked or embedded (e.g., PDFs with images).

        ### Usage:
        Used by the frontend when rendering previews that link to original embedded media.
        """,
        )
        async def download_document_media(document_uid: str, media_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                stream, file_name, content_type = await self.service.get_document_media(user, document_uid, media_id)

                return StreamingResponse(content=stream, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.get(
            "/raw_content/{document_uid}",
            tags=["Content"],
            summary="Download the original raw document content",
            response_class=StreamingResponse,  # <-- prevent default JSONResponse in OpenAPI
            responses={
                200: {
                    "description": "Binary file stream",
                    "content": {
                        # list the types you might emit; react-pdf likes application/pdf
                        "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                    },
                }
            },
        )
        async def download_document(document_uid: str, user: KeycloakUser = Depends(get_current_user)):
            stream, file_name, content_type = await self.service.get_original_content(user, document_uid)
            # Safety net: if your storage didn’t give a concrete type, fall back to octet-stream
            media_type = content_type or "application/octet-stream"

            # The original implementation for this endpoint likely already returns an iterable
            # or a synchronous file-like object that StreamingResponse can handle for simple downloads.
            # We assume it works as-is for the direct download use case.
            return StreamingResponse(
                content=stream,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
            )

        @router.get(
            "/raw_content/stream/{document_uid}",
            tags=["Content"],
            summary="Stream original document content (optimized for PDF Viewer and Range Requests)",
            response_class=StreamingResponse,
            responses={
                200: {"description": "Full binary file stream (no Range header)"},
                206: {"description": "Partial binary file stream (Range Request)"},
                416: {"description": "Range Not Satisfiable"},
            },
        )
        async def stream_document(
            document_uid: str,
            user: KeycloakUser = Depends(get_current_user),
            range_header: Optional[str] = Header(None, alias="Range"),
        ):
            try:
                file_meta = await self.service.get_file_metadata(user, document_uid)
                total_size = file_meta.size
                file_name = file_meta.file_name
                content_type = file_meta.content_type or "application/octet-stream"
                chunk_size = 8192  # Define a standard chunk size for streaming

                headers = {
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": f'inline; filename="{file_name}"',
                }

                rng = parse_range_header(range_header)

                # No Range → full file with Content-Length
                if rng is None:
                    raw_stream = await self.service.get_full_stream(user, document_uid)

                    # FIX: Wrap the non-iterable raw_stream object in an iterable generator
                    def stream_generator_200():
                        # Read chunks until the stream is exhausted
                        while chunk := raw_stream.read(chunk_size):
                            yield chunk

                    headers["Content-Length"] = str(total_size)
                    return StreamingResponse(
                        content=stream_generator_200(),  # Pass the generator
                        media_type=content_type,
                        headers=headers,
                        status_code=200,
                        background=BackgroundTask(getattr(raw_stream, "close", lambda: None)),
                    )

                # ---- Normalize Range window (inclusive end) ----
                start, end = rng

                if start is None and end is not None:
                    # Suffix: bytes=-N  (N may exceed total_size → serve whole file)
                    if end <= 0:
                        # invalid suffix
                        headers["Content-Range"] = f"bytes */{total_size}"
                        raise HTTPException(status_code=416, detail="Range Not Satisfiable")
                    start = max(total_size - end, 0)
                    end = total_size - 1
                else:
                    # Normal: bytes=START-END or bytes=START-
                    if start is None or start < 0 or start >= total_size:
                        headers["Content-Range"] = f"bytes */{total_size}"
                        raise HTTPException(status_code=416, detail="Range Not Satisfiable")
                    if end is None:
                        end = total_size - 1
                    else:
                        end = min(end, total_size - 1)
                    if end < start:
                        headers["Content-Range"] = f"bytes */{total_size}"
                        raise HTTPException(status_code=416, detail="Range Not Satisfiable")

                length = end - start + 1

                # Ask store for a stream that *clamps* to exactly `length` bytes
                raw_stream = await self.service.get_range_stream(user, document_uid, start=start, length=length)

                # FIX: Wrap the non-iterable raw_stream object in an iterable generator
                def stream_generator_206():
                    # Read chunks until the stream is exhausted
                    while chunk := raw_stream.read(chunk_size):
                        yield chunk

                headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
                # IMPORTANT: do NOT set Content-Length for 206 → avoids server crash on early client aborts
                return StreamingResponse(
                    content=stream_generator_206(),  # Pass the generator
                    media_type=content_type,
                    headers=headers,
                    status_code=206,
                    background=BackgroundTask(getattr(raw_stream, "close", lambda: None)),
                )

            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
