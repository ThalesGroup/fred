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


"""
ChromaDBVectorStore — embedded, local FS-backed implementation for Fred

Why this exists (Fred rationale):
- We want a zero-infra vector store for dev/demo/offline runs. Chroma's
  PersistentClient stores data on disk without a separate server or Docker.
- We keep Fred's BaseVectorStore contract so we can swap backends (OpenSearch,
  FAISS, Chroma) without touching calling code.
- Design choice: we compute embeddings via the caller-provided `Embeddings`
  (LangChain-like) to keep provider control (Azure, OpenAI, Ollama, HF).

Limitations & capabilities:
- Implements ANN (semantic) search and hydration (FetchById).
- Does NOT implement BM25/phrase search (LexicalSearchable) — Chroma doesn't
  ship lexical scoring. For hybrid, prefer OpenSearchVectorStore.

Data model expectations (same as the rest of Fred):
- Each chunk is a `Document` whose `metadata` contains:
  - `chunk_uid` (CHUNK_ID_FIELD): stable ID for idempotent upserts
  - `document_uid`: logical parent doc identity (for deletion by doc)

Scoring notes:
- Chroma returns distances; we convert cosine distance → similarity via
  `similarity = max(0.0, min(1.0, 1.0 - distance))` for a friendly [0,1] score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Mapping, Any
from datetime import datetime
import json

import chromadb
from langchain.schema.document import Document

# Fred base contracts
from app.core.stores.vector.base_embedding_model import BaseEmbeddingModel
from app.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    AnnHit,
    BaseVectorStore,
    FetchById,
    SearchFilter,
)

DOC_UID_FIELD = "document_uid"


def _assert_has_metadata_keys(doc: Document) -> None:
    if CHUNK_ID_FIELD not in (doc.metadata or {}):
        raise ValueError(f"Document is missing required metadata '{CHUNK_ID_FIELD}'")
    if DOC_UID_FIELD not in (doc.metadata or {}):
        raise ValueError(f"Document is missing required metadata '{DOC_UID_FIELD}'")


def _build_where(search_filter: Optional[SearchFilter]) -> Optional[Dict]:
    if not search_filter:
        return None
    where: Dict[str, Dict] = {}
    if search_filter.tag_ids:
        where[DOC_UID_FIELD] = {"$in": list(search_filter.tag_ids)}
    for k, values in (search_filter.metadata_terms or {}).items():
        where[k] = {"$in": list(values)}
    return where or None


def _cosine_similarity_from_distance(distance: float) -> float:
    # Chroma returns cosine distance; convert to [0,1] similarity for UI
    sim = 1.0 - float(distance)
    return max(0.0, min(1.0, sim))

def sanitize_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, list):
            # Empty list, returns None
            if not v:
                clean[k] = ""
            # List containing only one element, returns the element    
            elif len(v) == 1:
                clean[k] = v[0]
            # List containing more than one elements, returns a JSON string
            else:
                import json
                clean[k] = json.dumps(v)
        elif isinstance(v, Mapping):
            clean[k] = sanitize_metadata(v)
        else:
            clean[k] = v
    return clean


def restore_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, str):
            # Try to restore datetime
            try:
                restored[k] = datetime.fromisoformat(v)
                continue
            except ValueError:
                pass
            # Try to restore JSON-encoded lists
            try:
                loaded = json.loads(v)
                if isinstance(loaded, list):
                    restored[k] = loaded
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            restored[k] = v
        elif v == "":
            # originally empty list
            restored[k] = []
        else:
            restored[k] = v
    return restored


@dataclass
class ChromaDBVectorStore(BaseVectorStore, FetchById):
    """
    Embedded ChromaDB implementation of Fred's BaseVectorStore.

    Usage (dev-friendly, no server needed):
        store = ChromaDBVectorStore(
            persist_path=".fred_chroma",
            collection_name="fred_chunks",
            embeddings=azure_embedder,
        )
    """

    persist_path: str
    collection_name: str
    embeddings: BaseEmbeddingModel

    def __init__(self, persist_path: str, collection_name: str, embeddings: BaseEmbeddingModel) -> None:
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.embeddings = embeddings
        client = chromadb.PersistentClient(path=self.persist_path)
        self._collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # ensure cosine distance
        )

    # -------- Ingestion --------
    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        if not documents:
            return []
        # Validate metadata presence and build ids
        for d in documents:
            _assert_has_metadata_keys(d)
        chunk_ids: List[str] = ids or [str(d.metadata[CHUNK_ID_FIELD]) for d in documents]
        if len(chunk_ids) != len(documents):
            raise ValueError("len(ids) must match len(documents)")

        texts = [d.page_content for d in documents]
        metadatas = [sanitize_metadata(d.metadata) for d in documents]
        vectors = self.embeddings.embed_documents(texts)

        # Upsert for idempotency (add would error on duplicates)
        # Note: upsert is available in modern Chroma. If pinned older versions lack upsert,
        # you can fallback to delete(ids) + add(...), but that's less efficient.
        self._collection.add(
            ids=chunk_ids,
            embeddings=vectors,  # type: ignore[arg-type]
            documents=texts,
            metadatas=metadatas,  # type: ignore[arg-type]
        )
        return chunk_ids

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        self._collection.delete(where={DOC_UID_FIELD: document_uid})

    # -------- Search --------
    def ann_search(
        self,
        query: str,
        *,
        k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[AnnHit]:
        where = _build_where(search_filter)
        qvec = self.embeddings.embed_query(query)
        res = self._collection.query(
            query_embeddings=[qvec],
            n_results=k,
            where=where,
            include=["distances", "documents", "metadatas"],
        )
        # Chroma returns lists per query; we have one query
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        hits: List[AnnHit] = []
        for text, meta, dist in zip(docs, metas, dists):
            doc = Document(page_content=text, metadata=meta or {})
            hits.append(AnnHit(document=doc, score=_cosine_similarity_from_distance(dist)))
        return hits

    # -------- Hydration --------
    def fetch_documents(self, chunk_ids: Sequence[str]) -> List[Document]:
        if not chunk_ids:
            return []
        got = self._collection.get(ids=list(chunk_ids), include=["documents", "metadatas"])
        docs: List[Document] = []
        documents = got.get("documents", []) or []
        metadatas = got.get("metadatas", []) or []
        for text, meta in zip(documents, metadatas):
            docs.append(Document(
                page_content=text or "",
                metadata=restore_metadata(meta or {})
            ))
        return docs


__all__ = ["ChromaDBVectorStore", "DOC_UID_FIELD"]
