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
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from langchain.embeddings.base import Embeddings
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, AnnHit, BaseVectorStore, SearchFilter

logger = logging.getLogger(__name__)


# ----------------------- helpers -----------------------


def _to_json_safe(v: Any) -> Any:
    """Recursively make values JSON/Pydantic friendly."""
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, set):
        return list(v)
    if isinstance(v, dict):
        return {k: _to_json_safe(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_to_json_safe(x) for x in v]
    return v


def _normalize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    """Boundary normalization before storing metadata into the vector store."""
    md = dict(md or {})
    # Ensure known datetime fields are strings
    for key in ("created", "modified", "date_added_to_kb"):
        if key in md:
            md[key] = _to_json_safe(md[key])

    # Ensure tag_ids is always a list[str]
    tag_ids = md.get("tag_ids")
    if tag_ids is None:
        md["tag_ids"] = []
    elif isinstance(tag_ids, str):
        md["tag_ids"] = [tag_ids]
    else:
        md["tag_ids"] = [str(x) for x in list(tag_ids)]

    return _to_json_safe(md)


def _ensure_chunk_uid(md: Dict[str, Any]) -> str:
    """Return an existing chunk_uid or create a stable-ish one."""
    cid = md.get(CHUNK_ID_FIELD)
    if isinstance(cid, str) and cid:
        return cid
    # try to build from document_uid + chunk_index if present
    doc_uid = md.get("document_uid")
    cidx = md.get("chunk_index")
    if isinstance(doc_uid, str) and doc_uid and isinstance(cidx, int):
        cid = f"{doc_uid}::chunk::{cidx}"
    else:
        cid = str(uuid.uuid4())
    md[CHUNK_ID_FIELD] = cid
    return cid


# ----------------------- adapter -----------------------


class InMemoryLangchainVectorStore(BaseVectorStore):
    """
    In-Memory Vector Store (dev/test).
    - Pure ANN (no BM25/phrase).
    - Normalizes metadata to JSON-safe on ingestion.
    - Returns stable logical ids (chunk_uid), independent of LC internal keys.
    """

    def __init__(self, embedding_model: Embeddings, embedding_model_name: str) -> None:
        """
        embedding_model_name: used for metadata defaulting only.
        """
        self.embedding_model = embedding_model
        self.embedding_model_name = embedding_model_name
        self.vectorstore = InMemoryVectorStore(embedding=embedding_model)

    # ---- BaseVectorStore: ingestion ----

    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        """
        Upsert chunks (idempotent by chunk_uid). We do not rely on LC ids;
        we ensure/return metadata[chunk_uid] as the assigned id.
        """
        assigned: List[str] = []
        model_name = self.embedding_model_name or "unknown"

        # Normalize & ensure chunk_uid
        for d, forced_id in zip(documents, ids or [None] * len(documents)):
            d.metadata = _normalize_metadata(d.metadata or {})
            if isinstance(forced_id, str) and forced_id:
                d.metadata[CHUNK_ID_FIELD] = forced_id
            cid = _ensure_chunk_uid(d.metadata)
            assigned.append(cid)

            # nice-to-have defaults
            d.metadata.setdefault("embedding_model", model_name)
            d.metadata.setdefault("vector_index", "in-memory")
            # token_count is crude; good enough for dev
            d.metadata.setdefault("token_count", len((d.page_content or "").split()))
            d.metadata.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())

        # LC InMemoryVectorStore handles add; we don't pass our ids (they're logical)
        self.vectorstore.add_documents(documents)
        logger.info("✅ Added %d chunk(s) to in-memory store.", len(documents))

        # small debug peek
        for i, (doc_id, rec) in enumerate(self.vectorstore.store.items()):
            if i >= 3:
                break
            logger.debug("%s: %s", doc_id, rec.get("text"))

        return assigned

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        """
        Best-effort deletion: re-build store without records whose metadata.document_uid matches.
        (LC in-memory store has no public delete API; we mutate the underlying dict.)
        """
        try:
            to_delete = []
            for key, rec in self.vectorstore.store.items():
                md = rec.get("metadata") or {}
                if md.get("document_uid") == document_uid:
                    to_delete.append(key)
            for key in to_delete:
                del self.vectorstore.store[key]
            logger.info("✅ Deleted %d chunk(s) for document_uid=%s", len(to_delete), document_uid)
        except Exception:
            logger.exception("❌ Failed to delete vectors for document_uid=%s", document_uid)

    def get_document_chunk_count(self, *, document_uid: str) -> int:
        try:
            return sum(1 for rec in self.vectorstore.store.values() if (rec.get("metadata") or {}).get("document_uid") == document_uid)
        except Exception:
            logger.exception("❌ Failed to count chunks for document_uid=%s in memory store", document_uid)
            return 0

    def list_document_uids(self) -> List[str]:
        try:
            doc_uids: set[str] = set()
            for rec in self.vectorstore.store.values():
                uid = (rec.get("metadata") or {}).get("document_uid")
                if isinstance(uid, str) and uid:
                    doc_uids.add(uid)
            return sorted(doc_uids)
        except Exception:
            logger.warning("❌ Failed to list document_uids from in-memory store", exc_info=True)
            return []

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:
        """
        Dev-only: toggle retrievable flag on existing in-memory chunks without deleting them.
        """
        try:
            updated = 0
            for rec in self.vectorstore.store.values():
                md = rec.get("metadata") or {}
                if md.get("document_uid") == document_uid:
                    md["retrievable"] = bool(value)
                    rec["metadata"] = md
                    updated += 1
            logger.info(
                "✅ Updated retrievable=%s on %d in-memory chunks for document_uid=%s",
                value,
                updated,
                document_uid,
            )
        except Exception:
            logger.exception("❌ Failed to update retrievable flag for document_uid=%s in in-memory store", document_uid)

    # ---- BaseVectorStore: ANN ----

    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """
        ANN similarity search using LC's in-memory backend.
        Honors SearchFilter.document_ids by applying a callable filter.
        (metadata_terms are ignored here — no secondary index in dev store.)
        """
        lc_filter = None
        if search_filter and search_filter.tag_ids:
            allowed = set(search_filter.tag_ids)

            def _filter(doc: Document) -> bool:
                doc_uid = doc.metadata.get("document_uid")
                return isinstance(doc_uid, str) and doc_uid in allowed

            lc_filter = _filter

        pairs = self.vectorstore.similarity_search_with_score(query, k=k, filter=lc_filter)

        hits: List[AnnHit] = []
        model_name = self.embedding_model_name or "unknown"
        now_iso = datetime.now(timezone.utc).isoformat()

        for rank0, (doc, score) in enumerate(pairs, start=1):
            md = _normalize_metadata(doc.metadata or {})
            md.setdefault("embedding_model", model_name)
            md.setdefault("vector_index", "in-memory")
            md["score"] = float(score)
            md["rank"] = int(rank0)
            md["retrieved_at"] = now_iso
            md.setdefault("token_count", len((doc.page_content or "").split()))
            _ensure_chunk_uid(md)  # guarantee presence
            doc.metadata = md
            hits.append(AnnHit(document=doc, score=float(score)))

        return hits

    # ---- Introspection / Diagnostics ----
    def get_vectors_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        """
        Return all embeddings for the given document along with their chunk ids.

        Return format: [{"chunk_uid": str, "vector": list[float]}, ...]
        """
        try:
            out: List[Dict[str, Any]] = []
            # InMemoryVectorStore keeps a dict with records containing "embedding" if computed
            # and the original "metadata". We filter by metadata.document_uid.
            for key, rec in self.vectorstore.store.items():
                md = rec.get("metadata") or {}
                if md.get("document_uid") != document_uid:
                    continue
                vec = rec.get("embedding")
                if vec is None:
                    # The InMemory implementation may not expose the vector depending on the version.
                    # Skip entries without a vector to stay robust.
                    continue
                cid = md.get(CHUNK_ID_FIELD) or key
                out.append({"chunk_uid": cid, "vector": vec})
            logger.info("🔎 [InMemory] Retrieved %d vectors for document_uid=%s", len(out), document_uid)
            return out
        except Exception:
            logger.exception("❌ [InMemory] Failed to fetch vectors for document_uid=%s", document_uid)
            return []

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        """
        Return all chunks (text + metadata) for the given document.

        Return format: [{"chunk_uid": str, "text": str, "metadata": dict}, ...]
        """
        try:
            out: List[Dict[str, Any]] = []
            for key, rec in self.vectorstore.store.items():
                md = rec.get("metadata") or {}
                if md.get("document_uid") != document_uid:
                    continue
                text = rec.get("text", "")
                cid = md.get(CHUNK_ID_FIELD) or key
                out.append({"chunk_uid": cid, "text": text, "metadata": md})
            logger.info("📄 [InMemory] Retrieved %d chunks for document_uid=%s", len(out), document_uid)
            return out
        except Exception:
            logger.exception("❌ [InMemory] Failed to fetch chunks for document_uid=%s", document_uid)
            return []

    def get_chunk(self, document_uid: str, chunk_uid: str) -> Dict[str, Any]:
        """
        Return a single chunk (text + metadata) identified by chunk_uid within a document.

        Structure: { "chunk_uid": str, "text": str, "metadata": dict }
        """
        try:
            for key, rec in self.vectorstore.store.items():
                md = rec.get("metadata") or {}
                if md.get("document_uid") != document_uid:
                    continue
                cid = md.get(CHUNK_ID_FIELD) or key
                if cid == chunk_uid:
                    return {"chunk_uid": cid, "text": rec.get("text", ""), "metadata": md}
            logger.warning("🔎 [InMemory] Chunk not found: chunk_uid=%s document_uid=%s", chunk_uid, document_uid)
            return {"chunk_uid": chunk_uid}
        except Exception:
            logger.exception("❌ [InMemory] Failed to fetch chunk chunk_uid=%s for document_uid=%s", chunk_uid, document_uid)
            return {"chunk_uid": chunk_uid}

    def delete_chunk(self, document_uid: str, chunk_uid: str) -> None:
        """Delete a single chunk from the in-memory store."""
        try:
            to_delete_key = None
            for key, rec in self.vectorstore.store.items():
                md = rec.get("metadata") or {}
                if md.get("document_uid") != document_uid:
                    continue
                cid = md.get(CHUNK_ID_FIELD) or key
                if cid == chunk_uid:
                    to_delete_key = key
                    break
            if to_delete_key is not None:
                del self.vectorstore.store[to_delete_key]
                logger.info("🗑️  [InMemory] Deleted chunk chunk_uid=%s document_uid=%s", chunk_uid, document_uid)
            else:
                logger.warning("🗑️  [InMemory] Chunk to delete not found: chunk_uid=%s document_uid=%s", chunk_uid, document_uid)
        except Exception:
            logger.exception("❌ [InMemory] Failed to delete chunk chunk_uid=%s for document_uid=%s", chunk_uid, document_uid)
