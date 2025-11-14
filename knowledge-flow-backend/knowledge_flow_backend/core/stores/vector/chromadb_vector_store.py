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
# limitations under the License under the License.


"""
ChromaDBVectorStore — embedded, local FS-backed implementation for Fred
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

import chromadb
from chromadb.config import Settings
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

# Fred base contracts (assuming these exist in the environment)
from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    CHUNK_ID_FIELD,
    AnnHit,
    BaseVectorStore,
    FetchById,
    SearchFilter,
)

DOC_UID_FIELD = "document_uid"
# Configure logger for this module
logger = logging.getLogger(__name__)


def _assert_has_metadata_keys(doc: Document) -> None:
    if CHUNK_ID_FIELD not in (doc.metadata or {}):
        raise ValueError(f"Document is missing required metadata '{CHUNK_ID_FIELD}'")
    if DOC_UID_FIELD not in (doc.metadata or {}):
        raise ValueError(f"Document is missing required metadata '{DOC_UID_FIELD}'")


def _build_where(search_filter: Optional[SearchFilter]) -> Optional[Dict]:
    """
    Build the 'where' filter for Chroma.
    """
    if not search_filter:
        return None

    # Chroma's validate_where() requires that each where expression dict has
    # exactly one top-level operator key.
    clauses: List[Dict[str, Dict]] = []

    # ---- Tag IDs ----
    if search_filter.tag_ids:
        # Each tag is stored as a JSON array string
        tag_values = [json.dumps([t]) for t in search_filter.tag_ids]
        clauses.append({"tag_ids": {"$in": tag_values}})

    # ---- Metadata terms ----
    for field, values in (search_filter.metadata_terms or {}).items():
        encoded_values: List[Any] = []
        for v in values:
            if isinstance(v, list):
                # encode all lists as JSON strings
                encoded_values.append(json.dumps(v))
            else:
                encoded_values.append(v)
        clauses.append({field: {"$in": encoded_values}})

    if not clauses:
        return None

    # Show the built clauses before final compilation
    logger.debug(f"[SEARCH] Chroma filter clauses built: {clauses}")

    if len(clauses) == 1:
        return clauses[0]

    final_where = {"$and": clauses}
    # Show the final combined $and filter
    logger.debug(f"[SEARCH] Chroma final 'where' filter: {final_where}")

    return final_where


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
            # always JSON encode, even single element or empty
            json_encoded = json.dumps(v)
            clean[k] = json_encoded
            # Show how lists are encoded for storage
            logger.debug(f"[SEARCH] Field '{k}': List {v} encoded to string '{json_encoded}'")
        elif isinstance(v, Mapping):
            clean[k] = sanitize_metadata(v)
        else:
            clean[k] = v
    return clean


def restore_metadata(meta: Mapping[str, Any]) -> dict[str, Any]:
    restored: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, str):
            # Try to restore JSON-encoded lists (Chroma stores lists as JSON strings)
            try:
                loaded = json.loads(v)
                if isinstance(loaded, list):
                    restored[k] = loaded
                    # Show how lists are restored from storage
                    logger.debug(f"[SEARCH] Field '{k}': String '{v}' restored to List {loaded}")
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            restored[k] = v
        elif v == "":
            # Handle cases where an empty string might represent an originally empty list
            restored[k] = []
        else:
            restored[k] = v
    return restored


@dataclass
class ChromaDBVectorStore(BaseVectorStore, FetchById):
    """
    Embedded ChromaDB implementation of Fred's BaseVectorStore.
    """

    persist_path: str
    collection_name: str
    embeddings: Embeddings
    embedding_model_name: str

    def __init__(self, persist_path: str, collection_name: str, embeddings: Embeddings, embedding_model_name: str) -> None:
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.embeddings = embeddings
        self.embedding_model_name = embedding_model_name

        logger.info(f"[SEARCH] Initializing ChromaDB PersistentClient at path: {self.persist_path}")
        client = chromadb.PersistentClient(path=self.persist_path, settings=Settings(anonymized_telemetry=False))

        logger.info(f"[SEARCH] Getting or creating collection: {self.collection_name} with 'cosine' space.")
        self._collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # ensure cosine distance
        )

    # -------- Ingestion --------
    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        if not documents:
            logger.warning("[SEARCH] add_documents called with empty list. Returning early.")
            return []

        # Validate metadata presence and build ids
        texts = []
        metadatas = []
        chunk_ids: List[str] = ids or []

        logger.debug(f"[SEARCH] Processing {len(documents)} documents.")

        for i, d in enumerate(documents):
            _assert_has_metadata_keys(d)

            original_meta = d.metadata
            texts.append(d.page_content)

            # Sanitize and log metadata conversion
            sanitized = sanitize_metadata(original_meta)
            metadatas.append(sanitized)

            chunk_id = str(d.metadata[CHUNK_ID_FIELD])
            chunk_ids.append(chunk_id)

            logger.debug(f"[SEARCH] Document {i + 1} (ID: {chunk_id}):")
            logger.debug(f"[SEARCH]   - Original Metadata: {original_meta}")
            # The sanitize_metadata function handles logging the list conversions
            logger.debug(f"[SEARCH]   - **Sanitized (Stored) Metadata**: {sanitized}")

        if len(chunk_ids) != len(documents):
            raise ValueError("len(ids) must match len(documents)")

        # LOGGING: Indicate embedding step
        logger.debug(f"[SEARCH] Embedding {len(texts)} documents using model: {self.embedding_model_name}...")
        vectors = self.embeddings.embed_documents(texts)
        logger.debug(f"[SEARCH] Embedding complete. Vector dimension: {len(vectors[0]) if vectors else 'N/A'}")

        # Upsert for idempotency
        logger.debug(f"[SEARCH] Upserting {len(chunk_ids)} chunks into Chroma collection '{self.collection_name}'")
        self._collection.add(
            ids=chunk_ids,
            embeddings=vectors,  # type: ignore[arg-type]
            documents=texts,
            metadatas=metadatas,  # type: ignore[arg-type]
        )
        logger.debug("[SEARCH] Upsert successful.")
        return chunk_ids

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        # LOGGING: Show the delete operation
        logger.info(f"[SEARCH] Deleting vectors for document_uid: {document_uid} from collection '{self.collection_name}'")
        self._collection.delete(where={DOC_UID_FIELD: document_uid})
        logger.debug("[SEARCH] Delete operation sent to ChromaDB.")

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:
        """
        Update the 'retrievable' flag for all chunks of a document without deleting vectors.
        """
        try:
            logger.info(
                "[SEARCH] Updating retrievable=%s for all chunks of document_uid=%s in collection '%s'",
                value,
                document_uid,
                self.collection_name,
            )
            got = self._collection.get(where={DOC_UID_FIELD: document_uid}, include=["metadatas"])
            ids: List[str] = got.get("ids") or []
            metadatas: List[Mapping[str, Any]] = got.get("metadatas") or []
            if not ids:
                logger.info("[SEARCH] No chunks found for document_uid=%s when updating retrievable flag.", document_uid)
                return

            new_metadatas: List[Dict[str, Any]] = []
            for meta in metadatas:
                m: Dict[str, Any] = dict(meta or {})
                m["retrievable"] = bool(value)
                new_metadatas.append(m)

            self._collection.update(ids=ids, metadatas=new_metadatas)  # type: ignore[arg-type]
            logger.info(
                "[SEARCH] Updated retrievable=%s on %d chunks for document_uid=%s in collection '%s'",
                value,
                len(ids),
                document_uid,
                self.collection_name,
            )
        except Exception:
            logger.exception(
                "[SEARCH] Failed to update retrievable flag for document_uid=%s in collection '%s'",
                document_uid,
                self.collection_name,
            )
            raise

    # -------- Search --------
    def ann_search(
        self,
        query: str,
        *,
        k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[AnnHit]:
        """
        Perform semantic (ANN) search with optional filtering.
        """
        # Show the incoming query and parameters
        logger.debug(f"[SEARCH] Query: '{query[:50]}...', k={k}")
        logger.debug(f"[SEARCH] Requested Filter (SearchFilter object): {search_filter}")

        # ---- Build the Chroma 'where' filter ----
        where = _build_where(search_filter)

        # ---- Embed query ----
        logger.debug("[SEARCH] Embedding query...")
        query_vector = self.embeddings.embed_query(query)
        logger.debug(f"[SEARCH] Query vector generated: dimension={len(query_vector)}, model={self.embedding_model_name}")

        # ---- Query Chroma ----
        logger.debug(f"[SEARCH] Calling ChromaDB query: n_results={k}, where={where}")
        res = self._collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where=where,
            include=["distances", "documents", "metadatas"],
        )

        # LOGGING: Show the raw results summary from Chroma
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        if ids:
            logger.debug(f"[SEARCH] Top {len(ids)} IDs: {ids}")
            logger.debug(f"[SEARCH] Top {len(dists)} Distances: {[f'{d:.4f}' for d in dists]}")
        else:
            # Explicitly log when no documents are returned due to filtering/search
            logger.info("[SEARCH] NO DOCUMENTS RETURNED. Check 'where' filter consistency with stored metadata.")

        # ---- Extract results ----
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]

        hits: List[AnnHit] = []
        for i, (chunk_id, text, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            meta = meta or {}
            # This call triggers the restore metadata logs
            restored_meta = restore_metadata(meta)

            # Ensure tag_ids is always a list (even if it was stored as a single element)
            if "tag_ids" in restored_meta and not isinstance(restored_meta["tag_ids"], list):
                restored_meta["tag_ids"] = [restored_meta["tag_ids"]]

            doc = Document(page_content=text, metadata=restored_meta)
            hit = AnnHit(document=doc, score=_cosine_similarity_from_distance(dist))
            hits.append(hit)

            # LOGGING: Log the final hit details
            logger.debug(f"[SEARCH] [Hit {i + 1}] ID: {chunk_id}, Score: {hit.score:.4f} (Distance: {dist:.4f})")
            logger.debug(f"[SEARCH]   - Retrieved Text: {text[:50]}...")
            logger.debug(f"[SEARCH]   - **Final Restored Metadata**: {restored_meta}")

        logger.debug(f"[SEARCH] --- END: ANN Search complete. Returning {len(hits)} hits. ---")
        return hits

    # -------- Hydration --------
    def fetch_documents(self, chunk_ids: Sequence[str]) -> List[Document]:
        if not chunk_ids:
            logger.debug("[SEARCH] fetch_documents called with empty list. Returning early.")
            return []

        chunk_ids_list = list(chunk_ids)
        logger.debug(f"[SEARCH] Fetching {len(chunk_ids_list)} documents by chunk_id from collection '{self.collection_name}'")
        got = self._collection.get(ids=chunk_ids_list, include=["documents", "metadatas"])

        documents = got.get("documents", []) or []
        metadatas = got.get("metadatas", []) or []

        docs: List[Document] = []
        for text, meta in zip(documents, metadatas):
            restored_meta = restore_metadata(meta or {})
            docs.append(Document(page_content=text or "", metadata=restored_meta))
            logger.debug(f"[SEARCH] Retrieved chunk {restored_meta.get(CHUNK_ID_FIELD, 'N/A')}. Restored Metadata: {restored_meta}")

        logger.debug(f"[SEARCH] Fetch complete. Retrieved {len(docs)} documents.")
        return docs


__all__ = ["ChromaDBVectorStore", "DOC_UID_FIELD"]
