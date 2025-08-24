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
from app.contrib.eliccir.eliccir_vectorization_enricher import CirEnricher, merge_tags
from app.core.processors.output.base_output_processor import BaseOutputProcessor, VectorProcessingError
from app.core.processors.output.vectorization_processor.vectorization_utils import flat_metadata_from, load_langchain_doc_from_metadata, make_chunk_uid, sanitize_chunk_metadata

logger = logging.getLogger(__name__)


class VectorizationProcessor(BaseOutputProcessor):
    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.content_loader = self.context.get_content_store()
        self.splitter = self.context.get_text_splitter()
        self.embedder = self.context.get_embedder()
        self.vector_store = self.context.get_create_vector_store(self.embedder)
        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        # NEW: instantiate once
        self.cir_enricher = CirEnricher()
        # ... logging lines you already have

    @override
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            # 1) load
            document: Document = load_langchain_doc_from_metadata(file_path, metadata)
            # 2) split
            chunks = self.splitter.split(document)

            # 3) ensure doc uid ...
            doc_uid = metadata.document_uid
            base_flat = flat_metadata_from(metadata)
            base_flat = {k: v for k, v in base_flat.items() if v is not None}

            for i, doc in enumerate(chunks):
                raw_meta = (doc.metadata or {}).copy()
                raw_meta["chunk_index"] = i
                raw_meta.setdefault("original_doc_length", len(document.page_content))
                raw_meta["chunk_uid"] = make_chunk_uid(doc_uid, {**raw_meta, "chunk_index": i})

                # --- NEW: CIR enrichment on the chunk text ---
                text = doc.page_content or ""
                enrich = self.cir_enricher.enrich_text(text)

                # move forward with your sanitize step
                clean, dropped = sanitize_chunk_metadata(raw_meta)

                # --- merge CIR signals into metadata ---
                existing_tags = clean.get("tags") or base_flat.get("tags") or []
                cir_tags = [t.tag for t in enrich.tags]
                merged_tags = merge_tags(existing_tags, cir_tags)

                # keep a small sample of events at chunk level (UI timeline or later aggregation)
                cir_events = [
                    {
                        "kind": e.kind,
                        "date": e.date.isoformat() if e.date else None,
                        "snippet": e.snippet,
                    }
                    for e in enrich.events[:3]
                ]

                doc.metadata = {
                    **base_flat,
                    **clean,
                    "tags": merged_tags,
                    "cir_events": cir_events,
                }

                logger.info("[Chunk %d] tags=%s events=%d preview=%r", i, merged_tags, len(cir_events), text[:100])

            # 4) store embeddings
            self.vector_store.add_documents(chunks)

            metadata.mark_stage_done(ProcessingStage.VECTORIZED)
            metadata.mark_retrievable()
            return metadata

        except Exception as e:
            logger.exception("Unexpected error during vectorization")
            raise VectorProcessingError("vectorization processing failed") from e
