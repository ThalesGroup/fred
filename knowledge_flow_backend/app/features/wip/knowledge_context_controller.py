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

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from app.common.business_exception import (
    BusinessException,
    DocumentDeletionError,
    DocumentNotFound,
    DocumentProcessingError,
    KnowledgeContextError,
    KnowledgeContextDeletionError,
    KnowledgeContextNotFound,
    TokenLimitExceeded,
)
from app.common.utils import log_exception
from app.features.wip.knowledge_context_service import KnowledgeContextService
import tempfile
from pathlib import Path


class UpdateKnowledgeContextRequest(BaseModel):
    title: str
    description: str


class KnowledgeContextController:
    """
    Controller responsible for managing 'Knowledge Contexts'—custom document groupings 
    associated with user interactions, profiles, or projects.

    ⚠️ Transitional Design Notice:
    ------------------------------
    This controller represents an **early implementation** of contextual scoping for 
    document ingestion and retrieval. It was originally introduced to experiment with
    associating files to chat sessions or user projects in a structured way.

    However, the architecture is **evolving** toward a more robust and uniform system
    based on **tags**, which will handle:
      - user access control (RBAC)
      - project scoping
      - filtering/grouping of retrievable content

    As such, the current implementation:
      - persists knowledge contexts in a custom structure
      - allows uploading, updating, and deleting files tied to a context
      - supports markdown rendering and raw file access

    This controller should be treated as **temporary** and will likely be deprecated or 
    significantly refactored in the near future.

    Developers should not invest in extending this controller but focus instead on the 
    emerging `tag`-based metadata filtering system, which will subsume these use cases.

    Current Endpoints:
    ------------------
    - `GET /knowledgeContexts`: List all contexts for a tag
    - `GET /knowledgeContexts/{id}`: Fetch a context with markdown
    - `POST /knowledgeContexts`: Create a new context with documents
    - `PUT /knowledgeContexts/{id}`: Update metadata or attached files
    - `DELETE /knowledgeContexts/{id}`: Delete entire context
    - `DELETE /knowledgeContexts/{id}/documents/{doc_id}`: Delete a specific document

    Future Direction:
    -----------------
    The `knowledge_context_id` and `tag` mechanisms will be unified, with `tags` becoming 
    the central abstraction for organizing documents and enforcing visibility.
    """
    def __init__(self, router: APIRouter):
        self.service = KnowledgeContextService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.get("/knowledgeContexts")
        async def list_knowledge_contexts(tag: str = Query(...)):
            return await self.service.list_knowledge_contexts(tag)

        @router.get("/knowledgeContexts/{knowledgeContext_id}")
        async def get_knowledgeContext(knowledgeContext_id: str):
            try:
                return await self.service.get_knowledge_context_with_markdown(knowledgeContext_id)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="KnowledgeContext not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to load knowledgeContext: {str(e)}")

        @router.post("/knowledgeContexts")
        async def create_knowledge_context(
            title: str = Form(...), description: str = Form(...), files: list[UploadFile] = File(default=[]), tag: str = Form(...), file_descriptions: Optional[str] = Form(None)
        ):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    for f in files:
                        dest = tmp_path / f.filename
                        with open(dest, "wb") as out_file:
                            content = await f.read()
                            out_file.write(content)

                    file_desc_dict = json.loads(file_descriptions) if file_descriptions else {}
                    knowledgeContext = await self.service.create_knowledge_context(title, description, tmp_path, tag, file_desc_dict)
                    return knowledgeContext
            except TokenLimitExceeded:
                raise HTTPException(status_code=400, detail="Token limit exceeded")
            except DocumentProcessingError as e:
                raise HTTPException(status_code=500, detail=f"Could not process file: {e.filename}")
            except BusinessException as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                log_exception(e, "Unexpected error during knowledgeContext creation")
                raise HTTPException(status_code=500, detail="Internal Server Error")

        @router.put("/knowledgeContexts/{knowledgeContext_id}")
        async def update_knowledge_context(
            knowledgeContext_id: str, title: str = Form(...), description: str = Form(...), files: list[UploadFile] = File(default=[]), documents_description: str = Form(default="{}")
        ):
            try:
                parsed_descriptions = json.loads(documents_description)
                return await self.service.update_knowledge_context(knowledgeContext_id, title, description, files, parsed_descriptions)
            except KnowledgeContextNotFound as e:
                raise HTTPException(status_code=404, detail=str(e))
            except TokenLimitExceeded as e:
                raise HTTPException(status_code=400, detail=str(e))
            except DocumentProcessingError as e:
                raise HTTPException(status_code=500, detail=f"Failed to process one or more documents: {e}")
            except Exception as e:
                log_exception(e, f"Unexpected error while updating knowledgeContext {knowledgeContext_id}")
                raise HTTPException(status_code=500, detail="Unexpected server error during knowledgeContext update.")

        @router.delete("/knowledgeContexts/{knowledgeContext_id}")
        async def delete_knowledgeContext(knowledgeContext_id: str):
            try:
                return await self.service.delete_knowledge_context(knowledgeContext_id)
            except KnowledgeContextNotFound as e:
                raise HTTPException(status_code=404, detail=str(e))
            except KnowledgeContextDeletionError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except KnowledgeContextError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                log_exception(e, f"Unexpected error while deleting chat knowledgeContext {knowledgeContext_id}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @router.delete("/knowledgeContexts/{knowledgeContext_id}/documents/{document_id}")
        async def delete_document(knowledgeContext_id: str, document_id: str):
            try:
                return await self.service.delete_document(knowledgeContext_id, document_id)
            except KnowledgeContextNotFound as e:
                raise HTTPException(status_code=404, detail=str(e))
            except DocumentNotFound as e:
                raise HTTPException(status_code=404, detail=str(e))
            except DocumentDeletionError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except Exception as e:
                log_exception(e, f"Unexpected error deleting document '{document_id}' from knowledgeContext '{knowledgeContext_id}'")
                raise HTTPException(status_code=500, detail="Internal server error")
