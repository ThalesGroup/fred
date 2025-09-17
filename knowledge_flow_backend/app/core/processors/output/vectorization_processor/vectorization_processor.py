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
import os
import time
from typing import override

from fred_core import KPIActor, KPIWriter
from typing import List, Optional
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.common.document_structures import DocSummary, DocumentMetadata, ProcessingStage
from app.core.processors.output.base_output_processor import (
    BaseOutputProcessor,
    VectorProcessingError,
)
from app.core.processors.output.summarizer.smart_llm_summarizer import SmartDocSummarizer
from app.core.processors.output.vectorization_processor.vectorization_utils import (
    flat_metadata_from,
    load_langchain_doc_from_metadata,
    make_chunk_uid,
    sanitize_chunk_metadata,
)

logger = logging.getLogger(__name__)


class VectorizationProcessor(BaseOutputProcessor):
    """
    A pipeline for vectorizing documents.
    It orchestrates the loading, splitting, embedding, and storing of document vectors.
    Emits KPIs for duration, sizes, counts, and failures.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.content_loader = self.context.get_content_store()

        self.splitter = self.context.get_text_splitter()
        logger.info(f"✂️ Text splitter initialized: {self.splitter.__class__.__name__}")

        self.embedder = self.context.get_embedder()
        logger.info(f"🧠 Embedder initialized: {self.embedder.__class__.__name__}")

        self.smart_summarizer = SmartDocSummarizer(
            model_config=self.context.configuration.model,
            splitter=self.splitter,
            opts={  # hardcoded; move to config later
                "sum_enabled": True,
                "sum_input_cap": 120_000,
                "sum_abs_words": 180,
                "sum_kw_top_k": 24,
                "mr_top_shards": 24,
                "mr_shard_words": 80,
                "small_threshold": 50_000,
                "large_threshold": 1_200_000,
            },
        )

        self.vector_store = self.context.get_create_vector_store(self.embedder)
        logger.info(f"🗃️ Vector store initialized: {self.vector_store.__class__.__name__}")

        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        logger.info(f"📝 Metadata store initialized: {self.metadata_store.__class__.__name__}")

        self.kpi: KPIWriter = self.context.get_kpi_writer()  # preferred

    @override
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        t0 = time.perf_counter()
        # Pre-compute static KPI fields
        index_name = getattr(self.vector_store, "index_name", None) or getattr(self.vector_store, "index", None)
        file_type = getattr(metadata, "file_type", None) or (os.path.splitext(file_path)[1].lstrip(".") or None)
        doc_uid = None
        chunks_count = None
        vectors_count = None
        bytes_in = None

        # Try to grab file size (bytes_in) early; keep best-effort
        try:
            bytes_in = os.path.getsize(file_path)
        except Exception:
            bytes_in = None  # not fatal

        try:
            logger.info(f"Starting vectorization for {file_path}")

            document: Document = load_langchain_doc_from_metadata(file_path, metadata)
            logger.debug(f"Document loaded: {document}")
            if not document:
                raise ValueError("Document is empty or not loaded correctly.")

            # 1.b) Summarize ONCE per doc (size-aware; non-blocking)
            if self.context.is_summary_generation_enabled():
                abstract: Optional[str]
                keywords: Optional[List[str]]
                abstract, keywords = self.smart_summarizer.summarize_document(document)


                if abstract or keywords:
                    logger.info(
                        "Summaries computed: abstract_len=%d, keywords=%d",
                        len(abstract or ""), len(keywords or [])
                    )

                    # Fred rationale:
                    # - Keep human-facing abstract at *document* level (no chunk bloat).
                    # - Add provenance for audits and future refresh decisions.
                    metadata.summary = DocSummary(
                        abstract=abstract,
                        keywords=keywords or [],
                        model_name=self.smart_summarizer.get_model_name(),
                        method="SmartDocSummarizer@v1",
                        # created_at is set by the metadata store on save if you prefer; setting here is optional.
                    )


            # 2) Split
            chunks = self.splitter.split(document)
            chunks_count = len(chunks)
            logger.info(f"Document split into {chunks_count} chunks.")

            # 3) Ensure doc uid
            if not isinstance(metadata.document_uid, str) or not metadata.document_uid:
                raise ValueError("Metadata must contain a non-empty 'document_uid'.")
            doc_uid = metadata.document_uid

            # Build base metadata once and DROP Nones (important!)
            base_flat = flat_metadata_from(metadata)
            base_flat = {k: v for k, v in base_flat.items() if v is not None}

            # just before: for i, doc in enumerate(chunks):
            kw_for_search = None
            if keywords:
                # Fred rationale:
                # - Give BM25 a few strong tokens without duplicating the abstract.
                # - Keep it short to avoid index bloat.
                kw_for_search = " ".join((keywords or [])[:12])

            for i, doc in enumerate(chunks):
                raw_meta = (doc.metadata or {}).copy()

                # Ensure anchors BEFORE sanitize
                raw_meta["chunk_index"] = i
                raw_meta.setdefault("original_doc_length", len(document.page_content))

                # Stable id
                raw_meta["chunk_uid"] = make_chunk_uid(doc_uid, {**raw_meta, "chunk_index": i})

                # - Per-chunk 'doc_kw' boosts lexical recall for hybrid search.
                # - Name is short; ensure sanitize_chunk_metadata() whitelists 'doc_kw'.
                if kw_for_search:
                    raw_meta["doc_kw"] = kw_for_search

                # Whitelist + coerce + derive viewer_fragment/section
                clean, dropped = sanitize_chunk_metadata(raw_meta)

                # Merge with doc-level metadata
                doc.metadata = {**base_flat, **clean}

                logger.debug(
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
                # Heuristic: if add_documents returns ids/list, use its length as vectors_count; otherwise fall back to chunks_count
                if isinstance(result, (list, tuple, set)):
                    vectors_count = len(result)
                elif isinstance(result, dict) and "ids" in result and isinstance(result["ids"], list):
                    vectors_count = len(result["ids"])
                else:
                    vectors_count = chunks_count
                logger.debug(f"Documents added to Vector Store: {result}")
            except Exception as e:
                logger.exception("Failed to add documents to Vector Store")
                # Emit KPI with status=error before raising
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.kpi.vectorization_result(
                    doc_uid=doc_uid or "<unknown>",
                    file_type=file_type,
                    model=getattr(self.embedder, "model_name", None),
                    bytes_in=bytes_in,
                    chunks=chunks_count,
                    vectors=vectors_count,
                    duration_ms=duration_ms,
                    index=index_name,
                    status="error",
                    error_code="vectorstore_write_failed",
                    actor=KPIActor(type="system"),  # or "human", with user_id if relevant
                    scope_type="document",
                    scope_id=doc_uid,
                )
                raise VectorProcessingError("Failed to add documents to Vector Store") from e

            metadata.mark_stage_done(ProcessingStage.VECTORIZED)
            metadata.mark_retrievable()

            # Emit success KPI
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.kpi.vectorization_result(
                doc_uid=doc_uid,
                file_type=file_type,
                model=getattr(self.embedder, "model_name", None),
                bytes_in=bytes_in,
                chunks=chunks_count,
                vectors=vectors_count,
                duration_ms=duration_ms,
                index=index_name,
                status="ok",
                actor=KPIActor(type="system"),  # or "human", with user_id if relevant
                scope_type="document",
                scope_id=doc_uid,
            )
            return metadata

        except Exception as e:
            logger.exception("Unexpected error during vectorization")
            # Emit failure KPI for any other error path
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.kpi.vectorization_result(
                doc_uid=doc_uid or "<unknown>",
                file_type=file_type,
                model=getattr(self.embedder, "model_name", None),
                bytes_in=bytes_in,
                chunks=chunks_count,
                vectors=vectors_count,
                duration_ms=duration_ms,
                index=index_name,
                status="error",
                error_code=type(e).__name__,
                actor=KPIActor(type="system"),
                scope_type="document",
                scope_id=doc_uid,
            )
            raise VectorProcessingError("vectorization processing failed") from e
