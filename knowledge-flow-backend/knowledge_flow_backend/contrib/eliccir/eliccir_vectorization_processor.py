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
from typing import Any, Dict, List, Optional, override

from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext, get_app_context
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage
from knowledge_flow_backend.contrib.eliccir.eliccir_vectorization_enricher import CirEnricher, merge_tags
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor, VectorProcessingError
from knowledge_flow_backend.core.processors.output.vectorization_processor.vectorization_utils import flat_metadata_from, load_langchain_doc_from_metadata, make_chunk_uid, sanitize_chunk_metadata

logger = logging.getLogger(__name__)


class VectorizationProcessor(BaseOutputProcessor):
    """
    Eliccir-specific vectorization processor.

    Responsibilities:
    - Split markdown into semantic chunks.
    - Enrich chunk metadata with CIR tags/events.
    - Store embeddings in the configured vector store.
    - Optionally mirror document/chunk structure into Neo4j when MCP Neo4j is enabled.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.content_loader = self.context.get_content_store()
        self.splitter = self.context.get_text_splitter()
        self.embedder = self.context.get_embedder()
        self.vector_store = self.context.get_create_vector_store(self.embedder)
        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()
        self.cir_enricher = CirEnricher()

        # Optional: Neo4j graph mirroring for CIR documents.
        self.neo4j_driver = None
        try:
            # Reuse the shared driver from ApplicationContext if MCP Neo4j is enabled.
            if get_app_context().configuration.mcp.neo4j_enabled:
                self.neo4j_driver = self.context.get_neo4j_driver()
                logger.info("🕸️ Neo4j driver initialized for Eliccir vectorization processor.")
            else:
                logger.info("Neo4j MCP disabled in configuration; skipping graph mirroring.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j driver not available; CIR graph mirroring disabled: %s", exc)
            self.neo4j_driver = None

    @override
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            # 1) load
            document: Document = load_langchain_doc_from_metadata(file_path, metadata)

            # 2) split
            chunks = self.splitter.split(document)

            # 3) base metadata
            doc_uid = metadata.document_uid
            base_flat = flat_metadata_from(metadata)
            base_flat = {k: v for k, v in base_flat.items() if v is not None}

            for i, doc in enumerate(chunks):
                raw_meta = (doc.metadata or {}).copy()
                raw_meta["chunk_index"] = i
                raw_meta.setdefault("original_doc_length", len(document.page_content))
                raw_meta["chunk_uid"] = make_chunk_uid(doc_uid, {**raw_meta, "chunk_index": i})

                text = doc.page_content or ""
                enrich = self.cir_enricher.enrich_text(text)

                clean, _dropped = sanitize_chunk_metadata(raw_meta)

                existing_tags = clean.get("tags") or base_flat.get("tags") or []
                cir_tags = [t.tag for t in enrich.tags]
                merged_tags = merge_tags(existing_tags, cir_tags)

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

            # 4) store embeddings in the vector store
            self.vector_store.add_documents(chunks)

            # 5) optionally mirror to Neo4j graph
            if self.neo4j_driver is not None:
                try:
                    self._sync_to_neo4j(document=document, chunks=chunks, metadata=metadata)
                except Exception as exc:  # noqa: BLE001
                    # Graph mirroring is best-effort; do not fail ingestion on graph errors.
                    logger.error("Neo4j graph sync failed for document %s: %s", doc_uid, exc, exc_info=True)

            metadata.mark_stage_done(ProcessingStage.VECTORIZED)
            metadata.mark_retrievable()
            return metadata

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error during vectorization")
            raise VectorProcessingError("vectorization processing failed") from exc

    # -------------------------------------------------------------------------
    # Neo4j graph mirroring
    # -------------------------------------------------------------------------

    def _sync_to_neo4j(self, *, document: Document, chunks: List[Document], metadata: DocumentMetadata) -> None:
        """
        Mirror CIR-enriched chunks into Neo4j as a lightweight graph.

        Schema (subject to evolution):
          (:CirDocument {document_uid})-[:HAS_CHUNK {chunk_index}]->(:CirChunk {chunk_uid})
          (:CirChunk)-[:HAS_TAG]->(:CirTag {name})
          (:CirChunk)-[:HAS_EVENT]->(:CirEvent {event_id, kind, date, snippet})
        """
        if self.neo4j_driver is None:
            return

        doc_uid = metadata.document_uid
        doc_name: Optional[str] = getattr(metadata, "document_name", None)
        title: Optional[str] = getattr(metadata, "title", None)
        source_tag: Optional[str] = getattr(metadata, "source_tag", None)

        chunks_payload: List[Dict[str, Any]] = []
        for i, doc in enumerate(chunks):
            meta = doc.metadata or {}
            chunk_uid = meta.get("chunk_uid")
            if not chunk_uid:
                # Skip chunks without a stable id; they won't be addressable in the graph.
                logger.debug("Skipping chunk %d with no chunk_uid for document %s", i, doc_uid)
                continue

            text = doc.page_content or ""
            tags = meta.get("tags") or []
            events_meta = meta.get("cir_events") or []
            events_payload: List[Dict[str, Any]] = []
            for idx, ev in enumerate(events_meta):
                if not isinstance(ev, dict):
                    continue
                event_id = f"{chunk_uid}:{idx}"
                events_payload.append(
                    {
                        "event_id": event_id,
                        "kind": ev.get("kind"),
                        "date": ev.get("date"),
                        "snippet": ev.get("snippet"),
                    }
                )

            chunks_payload.append(
                {
                    "chunk_uid": chunk_uid,
                    "chunk_index": meta.get("chunk_index", i),
                    "text": text,
                    "tags": tags,
                    "events": events_payload,
                }
            )

        if not chunks_payload:
            logger.info("No chunks with chunk_uid found for document %s; skipping Neo4j sync.", doc_uid)
            return

        def _write_tx(tx, doc_uid_param: str, doc_name_param: Optional[str], title_param: Optional[str], source_tag_param: Optional[str], chunks_param: List[Dict[str, Any]]) -> None:
            # Upsert document node
            tx.run(
                """
                MERGE (d:CirDocument {document_uid: $doc_uid})
                SET d.document_name = coalesce($doc_name, d.document_name),
                    d.title = coalesce($title, d.title),
                    d.source_tag = coalesce($source_tag, d.source_tag)
                """,
                doc_uid=doc_uid_param,
                doc_name=doc_name_param,
                title=title_param,
                source_tag=source_tag_param,
            )

            # Upsert chunks, tags, and events
            tx.run(
                """
                MATCH (d:CirDocument {document_uid: $doc_uid})
                UNWIND $chunks AS ch
                MERGE (c:CirChunk {chunk_uid: ch.chunk_uid})
                SET c.text = ch.text,
                    c.chunk_index = ch.chunk_index,
                    c.document_uid = $doc_uid
                MERGE (d)-[:HAS_CHUNK {chunk_index: ch.chunk_index}]->(c)

                FOREACH (tag IN coalesce(ch.tags, []) |
                    MERGE (t:CirTag {name: tag})
                    MERGE (c)-[:HAS_TAG]->(t)
                )

                FOREACH (ev IN coalesce(ch.events, []) |
                    MERGE (e:CirEvent {event_id: ev.event_id})
                    SET e.kind = ev.kind,
                        e.date = ev.date,
                        e.snippet = ev.snippet,
                        e.document_uid = $doc_uid,
                        e.chunk_uid = ch.chunk_uid
                    MERGE (c)-[:HAS_EVENT]->(e)
                )
                """,
                doc_uid=doc_uid_param,
                chunks=chunks_param,
            )

        with self.neo4j_driver.session() as session:
            session.execute_write(_write_tx, doc_uid, doc_name, title, source_tag, chunks_payload)

        logger.info("Neo4j graph sync completed for document %s (chunks=%d).", doc_uid, len(chunks_payload))
