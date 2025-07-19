from fastapi import APIRouter, HTTPException, Query
from typing import List
from pydantic import BaseModel
from app.common.structures import DocumentMetadata
from app.features.pull.service import PullDocumentService, SourceNotFoundError


class PullDocumentsResponse(BaseModel):
    total: int
    documents: List[DocumentMetadata]


class PullDocumentController:
    """
    Controller responsible for listing synthetic or discovered metadata entries from pull sources.

    Pull sources are configured locations (e.g., folders, repositories, URLs) from which documents
    can be discovered but not necessarily uploaded yet. These entries represent candidate documents
    for ingestion.

    Endpoints:
    ----------
    - `GET /documents/pull`: returns a paginated list of `DocumentMetadata` entries, combining known ingested
      documents and synthetic placeholders for discovered but unprocessed files.

    Notes:
    ------
    - If a file has been previously ingested, its metadata will be returned.
    - If a file has been discovered but not ingested, a placeholder metadata is returned.
    - This endpoint does not modify any data or trigger ingestion.
    """

    def __init__(self, router: APIRouter):
        self.service = PullDocumentService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/documents/pull", tags=["Pull Documents"], response_model=PullDocumentsResponse)
        def list_pull_documents(
            source_tag: str = Query(..., description="The pull source tag to list documents from"),
            offset: int = Query(0, ge=0, description="Start offset for pagination"),
            limit: int = Query(50, gt=0, le=500, description="Maximum number of documents to return")
        ):
            try:
                documents, total = self.service.list_pull_documents(source_tag, offset=offset, limit=limit)
                return PullDocumentsResponse(documents=documents, total=total)
            except SourceNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
