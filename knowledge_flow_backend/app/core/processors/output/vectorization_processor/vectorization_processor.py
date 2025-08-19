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
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata, ProcessingStage
from app.core.processors.output.base_output_processor import BaseOutputProcessor, VectorProcessingError
from app.core.processors.output.vectorization_processor.vectorization_utils import flat_metadata_from, load_langchain_doc_from_metadata, make_chunk_uid, sanitize_chunk_metadata

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

        self.vector_store = self.context.get_create_vector_store(self.embedder)
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

            # 2) Split
            chunks = self.splitter.split(document)
            logger.info(f"Document split into {len(chunks)} chunks.")

            # 3) Ensure doc uid
            if not isinstance(metadata.document_uid, str) or not metadata.document_uid:
                raise ValueError("Metadata must contain a non-empty 'document_uid'.")
            doc_uid = metadata.document_uid

            # Build base metadata once and DROP Nones (important!)
            base_flat = flat_metadata_from(metadata)
            base_flat = {k: v for k, v in base_flat.items() if v is not None}  # <-- added

            for i, doc in enumerate(chunks):
                raw_meta = (doc.metadata or {}).copy()

                # Ensure anchors BEFORE sanitize
                raw_meta["chunk_index"] = i
                raw_meta.setdefault("original_doc_length", len(document.page_content))  # <-- added

                # Stable id
                raw_meta["chunk_uid"] = make_chunk_uid(doc_uid, {**raw_meta, "chunk_index": i})

                # Whitelist + coerce + derive viewer_fragment/section
                clean, dropped = sanitize_chunk_metadata(raw_meta)

                # Merge with doc-level metadata
                doc.metadata = {**base_flat, **clean}

                logger.info(
                    "[Chunk %d] preview=%r | idx=%s uid=%s cs=%s ce=%s section=%r dropped=%s",
                    i,
                    doc.page_content[:100],
                    doc.metadata.get("chunk_index"),
                    doc.metadata.get("chunk_uid"),
                    doc.metadata.get("char_start"),
                    doc.metadata.get("char_end"),
                    doc.metadata.get("section"),
                    dropped,
                )

            # 4) Store embeddings
            try:
                for i, doc in enumerate(chunks):
                    logger.debug("[Chunk %d] content=%r | meta=%s", i, doc.page_content[:100], doc.metadata)
                result = self.vector_store.add_documents(chunks)
                logger.debug(f"Documents added to Vector Store: {result}")
            except Exception as e:
                logger.exception("Failed to add documents to Vector Store")
                raise VectorProcessingError("Failed to add documents to Vector Store") from e

            metadata.mark_stage_done(ProcessingStage.VECTORIZED)
            metadata.mark_retrievable()
            return metadata

        except Exception as e:
            logger.exception("Unexpected error during vectorization")
            raise VectorProcessingError("vectorization processing failed") from e
