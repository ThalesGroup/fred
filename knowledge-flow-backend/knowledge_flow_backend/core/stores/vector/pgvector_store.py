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

from __future__ import annotations

import inspect
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from langchain_postgres.vectorstores import PGVector as NewPGVector  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without langchain-postgres
    NewPGVector = None

from langchain_community.vectorstores.pgvector import PGVector as LegacyPGVector
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sqlalchemy import create_engine, text

from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    AnnHit,
    BaseVectorStore,
    SearchFilter,
)

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """
    Recursively convert metadata values to JSON-safe types.
    - datetime/date -> ISO string
    - set/tuple -> list
    - objects -> string fallback
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    try:
        json.dumps(value)  # type: ignore[arg-type]
        return value
    except Exception:
        return str(value)


def _normalize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure metadata is JSON-serializable and contains stable ids.
    """
    md = dict(md or {})
    tag_ids = md.get("tag_ids")
    if tag_ids is None:
        md["tag_ids"] = []
    elif isinstance(tag_ids, str):
        md["tag_ids"] = [tag_ids]
    else:
        md["tag_ids"] = [str(x) for x in list(tag_ids)]
    return _json_safe(md)  # recursively make JSON-safe


def _ensure_chunk_uid(md: Dict[str, Any]) -> str:
    cid = md.get(CHUNK_ID_FIELD)
    if isinstance(cid, str) and cid:
        return cid
    doc_uid = md.get("document_uid")
    cidx = md.get("chunk_index")
    if isinstance(doc_uid, str) and doc_uid and isinstance(cidx, int):
        cid = f"{doc_uid}::chunk::{cidx}"
    else:
        cid = str(uuid.uuid4())
    md[CHUNK_ID_FIELD] = cid
    return cid


def _as_vector_list(vec: Any) -> Optional[List[float]]:
    """
    Best-effort conversion of a vector to a list[float], handling:
    - plain lists/tuples
    - numpy arrays
    - JSON-stringified lists (common when stored as text)
    """
    if vec is None:
        return None

    # Already a numeric iterable
    if isinstance(vec, (list, tuple)):
        try:
            return [float(v) for v in vec]
        except Exception:
            return None

    # Numpy array without importing globally
    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None
    if np is not None and isinstance(vec, np.ndarray):
        try:
            return [float(v) for v in vec.tolist()]
        except Exception:
            return None

    # JSON string representation
    if isinstance(vec, str):
        try:
            parsed = json.loads(vec)
            if isinstance(parsed, (list, tuple)):
                return [float(v) for v in parsed]
        except Exception:
            return None

    return None


class PgVectorStoreAdapter(BaseVectorStore):
    """
    PostgreSQL/pgvector-backed vector store via LangChain's PGVector.
    """

    def __init__(
        self,
        embedding_model: Embeddings,
        embedding_model_name: str,
        connection_string: str,
        collection_name: str,
    ) -> None:
        self.embedding_model = embedding_model
        self.embedding_model_name = embedding_model_name
        self.collection_name = collection_name
        self._connection_string = connection_string
        # lightweight engine for optional helper queries
        self._engine = create_engine(connection_string, future=True)
        self._vs = self._create_store(connection_string, collection_name)

    # ---------- BaseVectorStore: ingestion ----------

    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        assigned: List[str] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for d, forced_id in zip(documents, ids or [None] * len(documents)):
            d.metadata = _normalize_metadata(d.metadata or {})
            if isinstance(forced_id, str) and forced_id:
                d.metadata[CHUNK_ID_FIELD] = forced_id
            cid = _ensure_chunk_uid(d.metadata)
            assigned.append(cid)

            d.metadata.setdefault("embedding_model", self.embedding_model_name)
            d.metadata.setdefault("vector_index", self.collection_name)
            d.metadata.setdefault("ingested_at", now_iso)

        returned = self._vs.add_documents(documents, ids=assigned)
        logger.info(
            "[VECTOR][PGVECTOR] upserted %d chunk(s) into collection=%s",
            len(returned),
            self.collection_name,
        )
        return returned

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        """
        Remove all vectors for a logical document in this collection.
        Uses explicit SQL for observability and correctness.
        """
        try:
            with self._engine.begin() as conn:
                res = conn.execute(
                    text(
                        """
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid
                          AND c.name = :collection
                          AND e.cmetadata ? 'document_uid'
                          AND e.cmetadata ->> 'document_uid' = :doc_uid
                        """
                    ),
                    {"collection": self.collection_name, "doc_uid": document_uid},
                )
                deleted = res.rowcount or 0
                logger.info(
                    "[VECTOR][PGVECTOR] deleted vectors for document_uid=%s collection=%s deleted=%d",
                    document_uid,
                    self.collection_name,
                    deleted,
                )
        except Exception:
            logger.exception(
                "[VECTOR][PGVECTOR] failed to delete vectors for document_uid=%s",
                document_uid,
            )

    def get_document_chunk_count(self, *, document_uid: str) -> int:
        """
        Optional helper for admin UI: count chunks for a document in pgvector.
        """
        try:
            with self._engine.connect() as conn:
                res = conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = :collection
                          AND e.cmetadata ? 'document_uid'
                          AND e.cmetadata ->> 'document_uid' = :doc_uid
                        """
                    ),
                    {"doc_uid": document_uid, "collection": self.collection_name},
                ).scalar_one()
                return int(res)
        except Exception:
            logger.exception("[VECTOR][PGVECTOR] Failed to count chunks for %s", document_uid)
            return 0

    def list_document_uids(self) -> list[str]:
        """
        Optional helper for admin UI: list distinct document_uids.
        """
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT DISTINCT e.cmetadata ->> 'document_uid' AS doc_uid
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = :collection
                          AND e.cmetadata ? 'document_uid'
                        """
                    ),
                    {"collection": self.collection_name},
                ).fetchall()
                return [r[0] for r in rows if r[0]]
        except Exception:
            logger.exception("[VECTOR][PGVECTOR] Failed to list document_uids")
            return []

    def get_vectors_for_document(self, document_uid: str, with_document: bool = True) -> List[Dict[str, Any]]:
        """
        Return all vectors for a given document from langchain_pg_embedding.
        """
        try:
            sql = text(
                """
                SELECT e.custom_id, e.embedding, e.document, e.cmetadata
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = :collection
                  AND e.cmetadata ? 'document_uid'
                  AND e.cmetadata ->> 'document_uid' = :doc_uid
                """
            )
            with self._engine.connect() as conn:
                rows = conn.execute(sql, {"collection": self.collection_name, "doc_uid": document_uid}).fetchall()
            out: List[Dict[str, Any]] = []
            for cid, vec, doc, meta in rows:
                vec_list = _as_vector_list(vec)
                if vec_list is None:
                    logger.warning("[VECTOR][PGVECTOR] skipped vector for chunk_uid=%s (could not parse vector payload)", cid)
                    continue
                entry: Dict[str, Any] = {"chunk_uid": cid, "vector": vec_list}
                if with_document:
                    entry["text"] = doc or ""
                # Preserve normalized metadata when available
                if isinstance(meta, dict):
                    entry["metadata"] = meta
                out.append(entry)
            logger.info(
                "[VECTOR][PGVECTOR] fetched %d vectors for document_uid=%s collection=%s",
                len(out),
                document_uid,
                self.collection_name,
            )
            return out
        except Exception:
            logger.exception("[VECTOR][PGVECTOR] failed to fetch vectors for document_uid=%s", document_uid)
            return []

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        """
        Return all chunks (text + metadata) for the given document.
        """
        try:
            sql = text(
                """
                SELECT e.custom_id, e.document, e.cmetadata
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = :collection
                  AND e.cmetadata ? 'document_uid'
                  AND e.cmetadata ->> 'document_uid' = :doc_uid
                """
            )
            with self._engine.connect() as conn:
                rows = conn.execute(sql, {"collection": self.collection_name, "doc_uid": document_uid}).fetchall()
            out: List[Dict[str, Any]] = []
            for cid, doc, meta in rows:
                entry: Dict[str, Any] = {"chunk_uid": cid, "text": doc or "", "metadata": meta or {}}
                out.append(entry)
            logger.info(
                "[VECTOR][PGVECTOR] fetched %d chunks for document_uid=%s collection=%s",
                len(out),
                document_uid,
                self.collection_name,
            )
            return out
        except Exception:
            logger.exception("[VECTOR][PGVECTOR] failed to fetch chunks for document_uid=%s", document_uid)
            return []

    # ---------- BaseVectorStore: ANN search ----------

    def ann_search(
        self,
        query: str,
        *,
        k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[AnnHit]:
        filt: Dict[str, Any] = {}
        if search_filter:
            if search_filter.metadata_terms:
                for key, values in search_filter.metadata_terms.items():
                    if not values:
                        continue
                    # PGVector filter is equality-based; pick the first value
                    filt[key] = values[0]
            if search_filter.tag_ids:
                # Equality filter; best-effort match on the list
                filt["tag_ids"] = list(search_filter.tag_ids)

        filter_arg = filt or None
        logger.info(
            "[VECTOR][PGVECTOR][ANN] query=%r k=%d collection=%s filter=%s",
            query,
            k,
            self.collection_name,
            filter_arg,
        )
        try:
            hits = self._vs.similarity_search_with_relevance_scores(query, k=k, filter=filter_arg)
        except Exception:
            logger.exception(
                "[VECTOR][PGVECTOR] similarity search failed (k=%s, filter=%s)",
                k,
                filter_arg,
            )
            return []

        results: List[AnnHit] = []
        for doc, score in hits:
            if not doc or doc.metadata.get(CHUNK_ID_FIELD) is None:
                continue
            results.append(AnnHit(document=doc, score=score))
        logger.info(
            "[VECTOR][PGVECTOR][ANN] returned=%d top_score=%.4f",
            len(results),
            float(results[0].score) if results else 0.0,
        )
        return results

    def _create_store(self, connection_string: str, collection_name: str):
        """
        Instantiate the preferred pgvector implementation (langchain-postgres),
        and fall back to the legacy langchain_community version if unavailable.
        """
        if NewPGVector is not None:
            # Adapt to possible signature differences between versions.
            params = inspect.signature(NewPGVector.__init__).parameters
            kwargs: Dict[str, Any] = {}
            if "connection_string" in params:
                kwargs["connection_string"] = connection_string
            if "embeddings" in params:
                kwargs["embeddings"] = self.embedding_model
            elif "embedding_function" in params:
                kwargs["embedding_function"] = self.embedding_model
            if "collection_name" in params:
                kwargs["collection_name"] = collection_name
            if "use_jsonb" in params:
                kwargs["use_jsonb"] = True
            if "create_extension" in params:
                kwargs["create_extension"] = True
            try:
                store = NewPGVector(**kwargs)
                logger.info(
                    "[VECTOR][PGVECTOR] initialized (langchain-postgres) collection=%s",
                    collection_name,
                )
                return store
            except Exception:
                logger.exception("[VECTOR][PGVECTOR] Failed to init langchain-postgres PGVector, falling back to legacy implementation")

        # Legacy fallback
        store = LegacyPGVector(
            connection_string=connection_string,
            collection_name=collection_name,
            embedding_function=self.embedding_model,
            use_jsonb=True,
        )
        logger.info(
            "[VECTOR][PGVECTOR] initialized (legacy) collection=%s (default table)",
            collection_name,
        )
        return store
