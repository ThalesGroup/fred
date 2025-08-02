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
from typing import override
from fastapi import HTTPException
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.common.vectorization_utils import load_langchain_doc_from_metadata
from app.core.processors.output.base_output_processor import BaseOutputProcessor

logger = logging.getLogger(__name__)


class VectorizationProcessor(BaseOutputProcessor):
    """
    A pipeline for vectorizing documents.
    It orchestrates the loading, splitting, embedding, and storing of document vectors.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.content_loader = self.context.get_content_store()

        self.splitter = self.context.get_text_splitter()
        logger.info(f"✂️ Text splitter initialized: {self.splitter.__class__.__name__}")

        self.embedder = self.context.get_embedder()
        logger.info(f"🧠 Embedder initialized: {self.embedder.__class__.__name__}")

        self.vector_store = self.context.get_vector_store(self.embedder)
        logger.info(f"🗃️ Vector store initialized: {self.vector_store.__class__.__name__}")

        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        logger.info(f"📝 Metadata store initialized: {self.metadata_store.__class__.__name__}")

    @override
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            logger.info(f"Starting vectorization for {file_path}")
            
            document: Document = load_langchain_doc_from_metadata(file_path, metadata)
            logger.debug(f"Document loaded: {document}")
            if not document:
                raise ValueError("Document is empty or not loaded correctly.")
            # 2. Split the document
            chunks = self.splitter.split(document)
            logger.info(f"Document split into {len(chunks)} chunks.")

            # 3. Embed the chunks
            # embedded_chunks = embedder.embed_documents(chunks)
            # logger.info(f"{len(embedded_chunks)} chunks embedded.")

            # 4. Check if document already exists
            document_uid = metadata.document_uid
            if document_uid is None:
                raise ValueError("Metadata must contain a 'document_uid'.")

            # 5. Store embeddings
            try:
                for i, doc in enumerate(chunks):
                    logger.debug(f"[Chunk {i}] Document content preview: {doc.page_content[:100]!r} | Metadata: {doc.metadata}")
                result = self.vector_store.add_documents(chunks)
                logger.debug(f"Documents added to Vector Store: {result}")
            except Exception as e:
                logger.exception("Failed to add documents to Vectore Store: %s", e)
                raise HTTPException(status_code=500, detail="Failed to add documents to Vectore Store") from e
            metadata.mark_stage_done(ProcessingStage.VECTORIZED)
            return metadata

        except Exception as e:
            logger.exception(f"Error during vectorization: {e}")
            raise HTTPException(status_code=500, detail=str(e))
