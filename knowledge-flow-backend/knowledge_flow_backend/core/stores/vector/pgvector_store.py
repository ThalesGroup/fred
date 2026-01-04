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

import json
import logging
import uuid
import inspect
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

try:
    from langchain_postgres.vectorstores import PGVector as NewPGVector  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without langchain-postgres
    NewPGVector = None

from langchain_community.vectorstores.pgvector import PGVector as LegacyPGVector
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    AnnHit,
    BaseVectorStore,
    SearchFilter,
)
from sqlalchemy import create_engine, text

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
        try:
            self._vs.delete(filter={"document_uid": document_uid})
            logger.info("[VECTOR][PGVECTOR] deleted vectors for document_uid=%s", document_uid)
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
                        SELECT COUNT(*) FROM langchain_pg_embedding
                        WHERE cmetadata ? 'document_uid'
                          AND cmetadata ->> 'document_uid' = :doc_uid
                        """
                    ),
                    {"doc_uid": document_uid},
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
                        SELECT DISTINCT cmetadata ->> 'document_uid' AS doc_uid
                        FROM langchain_pg_embedding
                        WHERE cmetadata ? 'document_uid'
                        """
                    )
                ).fetchall()
                return [r[0] for r in rows if r[0]]
        except Exception:
            logger.exception("[VECTOR][PGVECTOR] Failed to list document_uids")
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
                logger.exception(
                    "[VECTOR][PGVECTOR] Failed to init langchain-postgres PGVector, falling back to legacy implementation"
                )

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
