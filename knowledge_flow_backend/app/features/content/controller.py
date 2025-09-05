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
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

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
    file_url: str = None
    modified: str = ""
    metadata: Dict[str, Any] = {}


class MarkdownContentResponse(BaseModel):
    content: str


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
        from app.features.content.service import ContentService

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
        async def get_markdown_preview(document_uid: str, _: KeycloakUser = Depends(get_current_user)):
            """
            Endpoint to retrieve a complete document including its content.
            """
            try:
                logger.info(f"Retrieving full document: {document_uid}")
                content = await self.service.get_markdown_preview(document_uid)
                return {"content": content}
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception:
                logger.exception("Unexpected error in get_document_preview")
                raise HTTPException(status_code=500, detail="Internal server error")

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
        async def download_document_media(document_uid: str, media_id: str, _: KeycloakUser = Depends(get_current_user)):
            try:
                stream, file_name, content_type = await self.service.get_document_media(document_uid, media_id)

                return StreamingResponse(content=stream, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception:
                logger.exception("Unexpected error in download_document")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.get(
            "/raw_content/{document_uid}",
            tags=["Content"],
            summary="Download the original raw document content",
            responses={
                200: {
                    "description": "Binary file stream",
                    "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
                }
            },
        )
        async def download_document(document_uid: str, _: KeycloakUser = Depends(get_current_user)):
            stream, file_name, content_type = await self.service.get_original_content(document_uid)
            return StreamingResponse(content=stream, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
