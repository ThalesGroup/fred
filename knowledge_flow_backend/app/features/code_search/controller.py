# app/features/code_search/controller.py
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.features.code_search.structures import CodeIndexProgress, CodeIndexRequest, CodeSearchRequest, CodeDocumentSource
from app.features.code_search.service import CodeSearchService
from langchain.schema.document import Document
from typing import List
from app.common.structures import Status

logger = logging.getLogger(__name__)

class CodeSearchController:
    def __init__(self, router: APIRouter):
        self.service = CodeSearchService()

        @router.post(
            "/code/search",
            tags=["Code Search"],
            summary="Search Java codebase using vectorization",
            response_model=List[CodeDocumentSource],
            operation_id="search_codebase"
        )
        def code_search(request: CodeSearchRequest):
            results = self.service.similarity_search_with_score(request.query, k=request.top_k)
            return [
                self._to_code_document_source(doc, score, rank)
                for rank, (doc, score) in enumerate(results, start=1)
            ]

        @router.post("/code/index", tags=["Code Search"])
        def index_codebase(request: CodeIndexRequest) -> StreamingResponse:
            def event_generator():
                try:
                    yield CodeIndexProgress(step="start", status=Status.SUCCESS, message=f"Starting scan of {request.path}").model_dump_json() + "\n"

                    docs = self.service.scan_codebase(request.path)
                    yield CodeIndexProgress(step="chunking", status=Status.SUCCESS, message=f"Split into {len(docs)} code chunks").model_dump_json() + "\n"

                    self.service.index_documents(docs)
                    yield CodeIndexProgress(step="embedding", status=Status.SUCCESS, message=f"Embedded and stored {len(docs)} documents").model_dump_json() + "\n"

                    yield CodeIndexProgress(step="done", status=Status.SUCCESS, message="Codebase indexed successfully").model_dump_json() + "\n"
                except Exception as e:
                    logger.exception("Error during code indexing")
                    yield CodeIndexProgress(step="error", status=Status.ERROR, error=str(e)).model_dump_json() + "\n"

            return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    def _to_code_document_source(self, doc: Document, score: float, rank: int) -> CodeDocumentSource:
        metadata = doc.metadata
        return CodeDocumentSource(
            content=doc.page_content,
            file_path=metadata.get("source", "Unknown"),
            file_name=metadata.get("file_name", "Unknown"),
            language=metadata.get("language", "Java"),
            symbol=metadata.get("symbol"),
            uid=metadata.get("document_uid", "Unknown"),
            score=score,
            rank=rank,
            embedding_model=str(metadata.get("embedding_model", "unknown_model")),
            vector_index=metadata.get("vector_index", "unknown_index"),
        )
