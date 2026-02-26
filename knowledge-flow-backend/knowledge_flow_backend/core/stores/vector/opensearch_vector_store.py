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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar

from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from opensearchpy import NotFoundError, OpenSearchException, RequestError

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, AnnHit, BaseVectorHit, BaseVectorStore, FullTextHit, HybridHit, SearchFilter

logger = logging.getLogger(__name__)
DEBUG = True


@dataclass(frozen=True)
class ExpectedIndexSpec:
    dim: int
    engine: str  # "lucene"
    space_type: str  # "cosinesimil"
    method_name: str  # "hnsw"


MODEL_INDEX_SPECS: dict[str, ExpectedIndexSpec] = {
    # OpenAI 3-series
    "text-embedding-3-large": ExpectedIndexSpec(dim=3072, engine="lucene", space_type="cosinesimil", method_name="hnsw"),
    "text-embedding-3-small": ExpectedIndexSpec(dim=1536, engine="lucene", space_type="cosinesimil", method_name="hnsw"),
    # Legacy (still supported but discouraged)
    "text-embedding-ada-002": ExpectedIndexSpec(dim=1536, engine="lucene", space_type="cosinesimil", method_name="hnsw"),
}

REQUIRED_METADATA_FIELDS: dict[str, Dict[str, str]] = {
    "session_id": {"type": "keyword"},
    "user_id": {"type": "keyword"},
    "scope": {"type": "keyword"},
}

HYBRID_SEARCH_PIPELINE_NAME = "hybrid-search-pipeline"

HYBRID_SEARCH_PIPELINE_CONFIG = {
    "description": "Post processor for hybrid search",
    "phase_results_processors": [{"normalization-processor": {"normalization": {"technique": "min_max"}, "combination": {"technique": "arithmetic_mean", "parameters": {"weights": [0.5, 0.5]}}}}],
}


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _norm_str(value: object) -> str:
    """Safely convert any mapping value (dict/None/str) to lowercase str."""
    if isinstance(value, dict):
        # Sometimes OpenSearch returns {"engine": "lucene"} instead of "lucene"
        return next(iter(value.values()), "").lower()
    if isinstance(value, (list, tuple)):
        return str(value[0]).lower() if value else ""
    return str(value or "").lower()


def _is_true_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return value is True


def _is_false_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "false"
    return value is False


T = TypeVar("T", bound=BaseVectorHit)


class OpenSearchVectorStoreAdapter(BaseVectorStore):
    """
    Fred — OpenSearch-backed Vector Store (LangChain for ANN + OS client for lexical/phrase).

    Why this shape:
      - Matches the minimal BaseVectorStore contract (ingest + ANN).
      - Keeps your existing LangChain usage; we only adapt the signatures + add 2 methods.
    """

    def __init__(
        self,
        embedding_model: Embeddings,
        embedding_model_name: str,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
        bulk_size: int = 1000,
    ):
        self._index = index
        self._embedding_model = embedding_model
        self._host = host
        self._username = username
        self._password = password
        self._secure = secure
        self._verify_certs = verify_certs
        self._bulk_size = bulk_size
        self._embedding_model_name = embedding_model_name
        self._vs: OpenSearchVectorSearch | None = None
        self._expected_dim: int | None = None

        if not self.pipeline_exists(pipeline_name=HYBRID_SEARCH_PIPELINE_NAME):
            self.create_pipeline(pipeline_name=HYBRID_SEARCH_PIPELINE_NAME, pipeline_config=HYBRID_SEARCH_PIPELINE_CONFIG)

        logger.info("[VECTOR][OPENSEARCH] initialized index=%r host=%r bulk=%s", self._index, self._host, self._bulk_size)

    # ---------- lazy LangChain wrapper + raw client ----------

    @property
    def _lc(self) -> OpenSearchVectorSearch:
        if self._vs is None:
            self._vs = OpenSearchVectorSearch(
                opensearch_url=self._host,
                index_name=self._index,
                embedding_function=self._embedding_model,
                use_ssl=self._secure,
                verify_certs=self._verify_certs,
                http_auth=(self._username, self._password),
                pool_maxsize=20,
                bulk_size=self._bulk_size,
            )
            self._expected_dim = self._get_embedding_dimension()
            self._validate_index_compatibility(self._expected_dim)
        return self._vs

    @property
    def _client(self):
        # low-level OpenSearch client for BM25/phrase
        return self._lc.client

    def validate_index_or_fail(self) -> None:
        """
        Force initialization + mapping validation so callers can fail fast at startup.
        """
        logger.info("[VECTOR][OPENSEARCH] validating vector index=%s", self._index)
        try:
            if self._vs is None:
                _ = self._lc  # triggers _validate_index_compatibility via lazy init
                return

            expected_dim = self._expected_dim or self._get_embedding_dimension()
            self._validate_index_compatibility(expected_dim)
        except ValueError as e:
            logger.critical("[VECTOR][OPENSEARCH] index validation failed: %s", e)
            raise SystemExit(1) from e

    def pipeline_exists(self, pipeline_name: str) -> bool:
        """
        Check whether a search pipeline exists in OpenSearch.

        Args:
            pipeline_name (str): Name of the OpenSearch search pipeline to check.

        Returns:
            bool: True if the pipeline exists, False if it does not exist or if an
            error occurs while checking.
        """
        try:
            self._lc.client.search_pipeline.get(id=pipeline_name)
            return True
        except NotFoundError:
            return False
        except Exception as e:
            logger.warning("[OPENSEARCH][PIPELINE] Error checking pipeline '%s': %s", pipeline_name, e)
            return False

    def create_pipeline(self, pipeline_name: str, pipeline_config: Dict[str, Any]) -> bool:
        """
        Create a search pipeline in OpenSearch if it does not already exist.

        Args:
            pipeline_name (str): Name of the OpenSearch search pipeline to create.
            pipeline_config (Dict[str, Any]): Configuration body of the search pipeline.

        Returns:
            bool: True if the pipeline was successfully created, False if the
            pipeline already exists.

        Raises:
            RequestError: If OpenSearch returns an error while creating the pipeline.
        """
        logger.info("[OPENSEARCH][PIPELINE] Creating pipeline '%s'", pipeline_name)

        try:
            self._lc.client.search_pipeline.put(id=pipeline_name, body=pipeline_config)
            logger.info("[OPENSEARCH][PIPELINE] Successfully created pipeline '%s'", pipeline_name)
            return True

        except RequestError as e:
            logger.error("[OPENSEARCH][PIPELINE] Failed to create pipeline '%s': %s", pipeline_name, e)
            raise

    # ---------- BaseVectorStore: identification ----------

    @property
    def index_name(self) -> Optional[str]:
        return self._index

    # ---------- BaseVectorStore: ingestion ----------

    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        """
        Idempotent upsert with stable ids (prefer metadata[chunk_uid]).
        Returns the assigned ids.
        """
        try:
            # If ids are not provided, derive them from metadata[chunk_uid]
            if ids is None:
                ids = []
                for d in documents:
                    cid = d.metadata.get(CHUNK_ID_FIELD)
                    if not cid:
                        raise ValueError(f"Document missing {CHUNK_ID_FIELD} in metadata")
                    ids.append(cid)

            assigned_ids = list(self._lc.add_documents(documents, ids=ids))
            model_name = self._embedding_model_name or "unknown"
            now_iso = datetime.now(timezone.utc).isoformat()

            # Normalize metadata (handy for UI/telemetry)
            for doc, cid in zip(documents, assigned_ids):
                if CHUNK_ID_FIELD not in doc.metadata:
                    doc.metadata[CHUNK_ID_FIELD] = cid
                doc.metadata.setdefault("embedding_model", model_name)
                doc.metadata.setdefault("vector_index", self._index)
                doc.metadata.setdefault("token_count", len((doc.page_content or "").split()))
                doc.metadata.setdefault("ingested_at", now_iso)

            logger.debug("[VECTOR][OPENSEARCH] upserted %s chunk(s) into %s", len(assigned_ids), self._index)
            return assigned_ids

        except Exception as e:
            logger.exception("[VECTOR][OPENSEARCH] failed to add documents to OpenSearch.")
            raise RuntimeError("Unexpected error during vector indexing.") from e

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        try:
            body = {"query": {"term": {"metadata.document_uid": {"value": document_uid}}}}
            resp = self._client.delete_by_query(index=self._index, body=body)
            deleted = int(resp.get("deleted", 0))
            logger.debug("[VECTOR][OPENSEARCH] deleted %s vector chunks for document_uid=%s.", deleted, document_uid)
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to delete vectors for document_uid=%s.", document_uid)
            raise RuntimeError("Failed to delete vectors from OpenSearch.")

    def get_document_chunk_count(self, *, document_uid: str) -> int:
        """
        Return the number of vector chunks stored for a given logical document.
        This is a convenience method used by diagnostic and visualization features.
        """
        try:
            body = {"query": {"term": {"metadata.document_uid": {"value": document_uid}}}}
            resp = self._client.count(index=self._index, body=body)
            count = int(resp.get("count", 0))
            logger.debug(
                "[VECTOR][OPENSEARCH] counted %s vector chunks for document_uid=%s in index=%s",
                count,
                document_uid,
                self._index,
            )
            return count
        except Exception:
            logger.exception(
                "[VECTOR][OPENSEARCH] failed to count vector chunks for document_uid=%s in index=%s",
                document_uid,
                self._index,
            )
            return 0

    def list_document_uids(self, *, max_buckets: int = 10000) -> List[str]:
        """
        Return distinct document_uids known to this vector index (best effort).
        """
        try:
            body = {
                "size": 0,
                "aggs": {"by_doc": {"terms": {"field": "metadata.document_uid", "size": max_buckets}}},
            }
            resp = self._client.search(index=self._index, body=body)
            buckets = resp.get("aggregations", {}).get("by_doc", {}).get("buckets", [])  # type: ignore[dict-item]
            return [str(b.get("key")) for b in buckets if b.get("key")]
        except Exception:
            logger.warning("[VECTOR][OPENSEARCH] Could not list document_uids from index=%s", self._index, exc_info=True)
            return []

    def set_document_retrievable(self, *, document_uid: str, value: bool) -> None:
        """
        Update the 'retrievable' flag for all chunks of a document without deleting vectors.
        This is used when a user toggles retrievability in the UI.
        """
        try:
            script = {
                "source": "ctx._source.metadata.retrievable = params.value",
                "lang": "painless",
                "params": {"value": bool(value)},
            }
            body = {
                "script": script,
                "query": {"term": {"metadata.document_uid": {"value": document_uid}}},
            }
            resp = self._client.update_by_query(
                index=self._index,
                body=body,
                params={"refresh": "true"},
            )
            updated = int(resp.get("updated", 0))
            logger.info(
                "[VECTOR][OPENSEARCH] updated retrievable=%s on %s vector chunks for document_uid=%s.",
                value,
                updated,
                document_uid,
            )
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to update retrievable flag for document_uid=%s.", document_uid)
            raise RuntimeError("Failed to update retrievable flag in OpenSearch.")

    # ---------- Diagnostics / Introspection ----------

    def get_vectors_for_document(self, document_uid: str, with_document: bool = True) -> List[Dict[str, Any]]:
        """
        Return all vectors for the given document. Depending on index mapping, the raw vector
        may or may not be stored in _source. If not available, entries without vectors are skipped.

        Returns: [{"chunk_uid": str, "vector": list[float], (optional) "text": str}]
        """
        try:
            body = {
                "size": 10000,
                "query": {"term": {"metadata.document_uid": {"value": document_uid}}},
                "_source": ["vector_field", "text"],
            }
            res = self._client.search(index=self._index, body=body)
            hits = res.get("hits", {}).get("hits", [])
            out: List[Dict[str, Any]] = []
            for h in hits:
                src = h.get("_source", {}) or {}
                vec = src.get("vector_field")
                if vec is None:
                    # vector might not be stored in _source
                    continue
                entry: Dict[str, Any] = {"chunk_uid": h.get("_id"), "vector": vec}
                if with_document:
                    entry["text"] = src.get("text", "")
                out.append(entry)
            logger.debug(
                "[VECTOR][OPENSEARCH] fetched %d vectors for document_uid=%s from index=%s",
                len(out),
                document_uid,
                self._index,
            )
            return out
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to fetch vectors for document_uid=%s", document_uid)
            return []

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        """
        Return all chunks (text + metadata) for the given document.

        Returns: [{"chunk_uid": str, "text": str, "metadata": dict}]
        """
        try:
            body = {
                "size": 10000,
                "query": {"term": {"metadata.document_uid": {"value": document_uid}}},
                "_source": ["text", "metadata"],
            }
            res = self._client.search(index=self._index, body=body)
            hits = res.get("hits", {}).get("hits", [])
            out: List[Dict[str, Any]] = []
            for h in hits:
                src = h.get("_source", {}) or {}
                out.append(
                    {
                        "chunk_uid": h.get("_id"),
                        "text": src.get("text", ""),
                        "metadata": src.get("metadata", {}) or {},
                    }
                )
            logger.debug(
                "[VECTOR][OPENSEARCH] fetched %d chunks for document_uid=%s from index=%s",
                len(out),
                document_uid,
                self._index,
            )
            return out
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to fetch chunks for document_uid=%s", document_uid)
            return []

    def get_chunk(self, document_uid: str, chunk_uid: str) -> Dict[str, Any]:
        """
        Return a single chunk (text + metadata) if it belongs to the given document.
        """
        try:
            res = self._client.get(index=self._index, id=chunk_uid)
            if not res or res.get("found") is not True:
                logger.warning("[VECTOR][OPENSEARCH] chunk not found: %s", chunk_uid)
                return {"chunk_uid": chunk_uid}
            src = res.get("_source", {}) or {}
            md = src.get("metadata", {}) or {}
            if md.get("document_uid") != document_uid:
                logger.warning(
                    "[VECTOR][OPENSEARCH] chunk %s does not belong to document_uid=%s",
                    chunk_uid,
                    document_uid,
                )
                return {"chunk_uid": chunk_uid}
            return {
                "chunk_uid": chunk_uid,
                "text": src.get("text", ""),
                "metadata": md,
            }
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to fetch chunk %s", chunk_uid)
            return {"chunk_uid": chunk_uid}

    def delete_chunk(self, document_uid: str, chunk_uid: str) -> None:
        """Delete a single chunk by id; if it doesn't belong to the given document, do nothing."""
        try:
            # Ensure ownership by checking metadata.document_uid
            res = self._client.get(index=self._index, id=chunk_uid)
            if not res or res.get("found") is not True:
                logger.warning("[VECTOR][OPENSEARCH] cannot delete; chunk not found: %s", chunk_uid)
                return
            src = res.get("_source", {}) or {}
            md = src.get("metadata", {}) or {}
            if md.get("document_uid") != document_uid:
                logger.warning(
                    "[VECTOR][OPENSEARCH] not deleting chunk %s: mismatched document_uid=%s",
                    chunk_uid,
                    document_uid,
                )
                return
            self._client.delete(index=self._index, id=chunk_uid)
            logger.debug("[VECTOR][OPENSEARCH] deleted chunk %s for document_uid=%s", chunk_uid, document_uid)
        except Exception:
            logger.exception("[VECTOR][OPENSEARCH] failed to delete chunk %s for document_uid=%s", chunk_uid, document_uid)

    def _build_hits(self, hits_data: List, hit_type: Type[T]) -> List[T]:
        """
        Build a list of hit objects from OpenSearch hits data.

        Args:
            hits_data (List): Raw hit data from OpenSearch search results.
            hit_type (Type[T]): The type of hit object to construct.

        Returns:
            List[T]: A list of constructed hit objects.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        model_name = self._embedding_model_name or "unknown"
        results: List[T] = []

        for rank, h in enumerate(hits_data, start=1):
            src = h.get("_source", {})
            meta = src.get("metadata", {})
            text = src.get("text", "")
            cid = meta.get(CHUNK_ID_FIELD) or h.get("_id")

            logger.debug(
                "[VECTOR][OPENSEARCH] hit rank=%d doc_uid=%s chunk_uid=%s retrievable=%s score=%.4f",
                rank,
                meta.get("document_uid"),
                cid,
                meta.get("retrievable"),
                float(h.get("_score", 0.0)),
            )

            doc = Document(
                page_content=text,
                metadata={
                    **meta,
                    CHUNK_ID_FIELD: cid,
                    "score": float(h.get("_score", 0.0)),
                    "rank": rank,
                    "retrieved_at": now_iso,
                    "embedding_model": model_name,
                    "vector_index": self._index,
                    "token_count": len(text.split()),
                },
            )

            results.append(hit_type(document=doc, score=float(h.get("_score", 0.0))))

        return results

    # ---- helpers ----------------------------------------------------------
    def _build_ann_hits(self, hits_data: List) -> List[AnnHit]:
        hits = self._build_hits(hits_data, AnnHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][OPENSEARCH][ANN] built hits count=%d sample=%s", len(hits), hits[:3])
        return hits

    def _build_hybrid_hits(self, hits_data: List) -> List[HybridHit]:
        hits = self._build_hits(hits_data, HybridHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][OPENSEARCH][HYBRID] built hits count=%d sample=%s", len(hits), hits[:3])
        return hits

    def _build_fulltext_hits(self, hits_data: list) -> List[FullTextHit]:
        hits = self._build_hits(hits_data, FullTextHit)
        if DEBUG and hits:
            logger.debug("[VECTOR][OPENSEARCH][FULLTEXT] built hits count=%d sample=%s", len(hits), hits[:3])
        return hits

    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """
        Perform an approximate nearest neighbor (ANN) search in the OpenSearch index.

        Args:
            query (str): The search query string to embed and search for.
            k (int): The number of top results to return.
            search_filter (Optional[SearchFilter]): Optional filter to apply to the search.

        Returns:
            List[AnnHit]: A list of AnnHit objects representing the search results.

        Raises:
            RuntimeError: If the embedding model fails or if the search query fails.
        """
        logger.debug("[VECTOR][OPENSEARCH][ANN] query=%r k=%d search_filter=%s", query, k, search_filter)
        filters = self._to_filter_clause(search_filter)
        logger.debug("[VECTOR][OPENSEARCH][ANN] computed filters=%s", filters or [])

        try:
            vector = self._embedding_model.embed_query(query)
            logger.debug("[VECTOR][OPENSEARCH][ANN] embedding_dim=%d", len(vector))
        except Exception as e:
            logger.exception("[VECTOR][OPENSEARCH] failed to compute embedding.")
            raise RuntimeError("Embedding model failed.") from e

        knn_query = {
            "vector": vector,
            "k": k,
        }

        if filters:
            knn_query["filter"] = {"bool": {"filter": filters}}

        bool_knn_body = {
            "size": k,
            "query": {"knn": {"vector_field": knn_query}},
            "_source": True,
        }

        try:
            res = self._client.search(index=self._index, body=bool_knn_body)
            hits_data = res.get("hits", {}).get("hits", [])
            logger.debug("[VECTOR][OPENSEARCH][ANN] search returned %d hits", len(hits_data))
            if hits_data:
                sample = [
                    {
                        "chunk_id": h["_source"].get("chunk_id"),
                        "score": h.get("_score"),
                        "metadata": h["_source"].get("metadata", {}),
                    }
                    for h in hits_data[:3]
                ]
                logger.debug("[VECTOR][OPENSEARCH][ANN] top hits sample=%s", sample)
            else:
                filter_only = {"size": 3, "query": {"bool": {"filter": filters}}} if filters else {"size": 3, "query": {"match_all": {}}}
                try:
                    debug_res = self._client.search(index=self._index, body=filter_only)
                    debug_hits = debug_res.get("hits", {}).get("hits", [])
                    sample = [
                        {
                            "chunk_id": h["_source"].get("chunk_id"),
                            "has_vector": "vector_field" in h["_source"],
                            "metadata": h["_source"].get("metadata", {}),
                        }
                        for h in debug_hits
                    ]
                    logger.debug(
                        "[VECTOR][OPENSEARCH][ANN] 0 KNN hits; filter-only match count=%d sample=%s",
                        len(debug_hits),
                        sample,
                    )
                except Exception as e:
                    logger.warning("[VECTOR][OPENSEARCH][ANN] filter-only debug query failed: %s", e)
        except Exception as e:
            logger.warning("[VECTOR][OPENSEARCH][ANN] query failed: %s", str(e))
            raise OpenSearchException(f"{str(e)}") from e

        return self._build_ann_hits(hits_data)

    def hybrid_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[HybridHit]:
        """
        Perform a hybrid search combining full-text and vector search in the OpenSearch index.

        Args:
            query (str): The search query string to use for both full-text and vector search.
            top_k (int): The number of top results to return.
            search_filter (Optional[SearchFilter]): Optional filter to apply to the search.

        Returns:
            List[HybridHit]: A list of HybridHit objects representing the hybrid search results.

        Raises:
            OpenSearchException: If the search query fails.
        """
        filters = self._to_filter_clause(search_filter)

        def _build_match_query(query: str, filters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            if not filters:
                return {"match": {"text": {"query": query}}}

            return {"bool": {"must": [{"match": {"text": {"query": query}}}], "filter": filters}}

        def _build_knn_query(embedding_vector: List[float], k: int, filters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            knn_query = {
                "knn": {
                    "vector_field": {
                        "vector": embedding_vector,
                        "k": k,
                    }
                }
            }

            if filters:
                knn_query["knn"]["vector_field"]["filter"] = {"bool": {"filter": filters}}

            return knn_query

        embedding_vector = self._embedding_model.embed_query(query)
        search_body = {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        _build_match_query(query, filters),
                        _build_knn_query(embedding_vector, top_k * 2, filters),
                    ]
                }
            },
        }

        try:
            response = self._client.search(index=self._index, body=search_body, params={"search_pipeline": HYBRID_SEARCH_PIPELINE_NAME})
            hits_data = response.get("hits", {}).get("hits", [])
            logger.debug("[VECTOR][OPENSEARCH][HYBRID] search returned %d hits", len(hits_data))
            if DEBUG and hits_data:
                sample = [
                    {
                        "chunk_id": h["_source"].get("chunk_id"),
                        "score": h.get("_score"),
                        "metadata": h["_source"].get("metadata", {}),
                    }
                    for h in hits_data[:3]
                ]
                logger.debug("[VECTOR][OPENSEARCH][HYBRID] top hits sample=%s", sample)
        except Exception as e:
            logger.warning("[VECTOR][OPENSEARCH][HYBRID] query failed: %s", str(e))
            raise OpenSearchException(f"{str(e)}") from e

        return self._build_hybrid_hits(hits_data=hits_data)

    def full_text_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[FullTextHit]:
        """
        Perform a full-text search in the OpenSearch index.

        Args:
            query (str): The search query string to use for full-text search.
            top_k (int): The number of top results to return.
            search_filter (Optional[SearchFilter]): Optional filter to apply to the search.

        Returns:
            List[FullTextHit]: A list of FullTextHit objects representing the full-text search results.

        Raises:
            OpenSearchException: If the search query fails.
        """
        filters = self._to_filter_clause(search_filter)

        if filters:
            search_body = {"size": top_k, "query": {"bool": {"must": [{"match": {"text": {"query": query}}}], "filter": filters}}}
        else:
            search_body = {"size": top_k, "query": {"match": {"text": {"query": query}}}}

        try:
            response = self._client.search(index=self._index, body=search_body)
            hits_data = response.get("hits", {}).get("hits", [])
            logger.debug("[VECTOR][OPENSEARCH][FULLTEXT] search returned %d hits", len(hits_data))
            if DEBUG and hits_data:
                sample = [
                    {
                        "chunk_id": h["_source"].get("chunk_id"),
                        "score": h.get("_score"),
                        "metadata": h["_source"].get("metadata", {}),
                    }
                    for h in hits_data[:3]
                ]
                logger.debug("[VECTOR][OPENSEARCH][FULLTEXT] top hits sample=%s", sample)
        except Exception as e:
            logger.warning("[VECTOR][OPENSEARCH][FULLTEXT] query failed: %s", str(e))
            raise OpenSearchException(f"{str(e)}") from e

        return self._build_fulltext_hits(hits_data=hits_data)

    # ---------- helpers ----------

    def _apply_metadata_mapping_updates(self, missing_fields: List[str]) -> bool:
        """
        Try to add missing metadata keyword fields so the attachment/session filters continue to work.
        """
        payload = {"properties": {"metadata": {"properties": {field: {"type": REQUIRED_METADATA_FIELDS[field]["type"]} for field in missing_fields if field in REQUIRED_METADATA_FIELDS}}}}
        try:
            self._client.indices.put_mapping(index=self._index, body=payload)
            logger.info(
                "[VECTOR][OPENSEARCH][MAPPING] added missing metadata fields %s to index %s",
                missing_fields,
                self._index,
            )
            return True
        except Exception as exc:
            logger.error(
                "[VECTOR][OPENSEARCH][MAPPING] failed to add metadata fields %s to index %s: %s",
                missing_fields,
                self._index,
                exc,
            )
            return False

    def _get_embedding_dimension(self) -> int:
        dummy_vector = self._embedding_model.embed_query("dummy")
        return len(dummy_vector)

    def _validate_index_compatibility(self, expected_dim: int, allow_metadata_mapping_update: bool = True):
        """
        Fred rationale:
        - We fail fast if index mapping cannot faithfully serve the configured embedding model.
        - Checks: vector dimension, engine, space type, and HNSW method.
        """
        try:
            mapping = self._client.indices.get_mapping(index=self._index)
        except Exception as e:
            logger.warning("[VECTOR][OPENSEARCH] could not fetch mapping for %r: %s", self._index, e)
            return  # Don't block init; ANN calls will fail later with clearer errors.

        m = mapping.get(self._index, {}).get("mappings", {})
        actual_dim = _safe_get(m, ["properties", "vector_field", "dimension"])
        method_engine = _norm_str(_safe_get(m, ["properties", "vector_field", "method", "engine"]))
        method_space = _norm_str(_safe_get(m, ["properties", "vector_field", "method", "space_type"]))
        method_name = _norm_str(_safe_get(m, ["properties", "vector_field", "method", "name"]))

        model_name = self._embedding_model_name or "unknown"
        spec = MODEL_INDEX_SPECS.get(model_name)

        # If we don't know the model, fall back to the dimension we probed.
        if spec is None:
            spec = ExpectedIndexSpec(dim=expected_dim, engine="lucene", space_type="cosinesimil", method_name="hnsw")

        problems: list[str] = []
        warnings: list[str] = []

        # 1) Dimension
        if actual_dim != spec.dim:
            problems.append(f"- Dimension mismatch: index has {actual_dim}, model '{model_name}' requires {spec.dim}.")

        # 2) Engine (we standardize on lucene)
        if (method_engine or "") != spec.engine:
            if (method_engine or "").lower() == "nmslib":
                warnings.append("- Engine mismatch: index uses 'nmslib', expected 'lucene'. Continuing for backward compatibility, but expect reduced recall and less reliable filtering.")
            else:
                problems.append(f"- Engine mismatch: index uses '{method_engine}', expected '{spec.engine}'. Lucene is recommended; nmslib may degrade recall and complicate filters.")

        # 3) Space type (cosine for OpenAI)
        if (method_space or "") != spec.space_type:
            msg = f"- Space mismatch: index uses '{method_space}', expected '{spec.space_type}' for OpenAI embeddings."
            if (method_space or "").lower() in {"l2", "euclidean"}:
                # Do not hard fail to stay compatible with old indices, but warn loudly.
                warnings.append(f"{msg} L2 is deprecated; reindex with '{spec.space_type}'. Until then, L2-normalize vectors at ingest and query time.")
            else:
                problems.append(msg)

        # 4) Method name (HNSW)
        if (method_name or "") != spec.method_name:
            problems.append(f"- Method mismatch: index uses '{method_name}', expected '{spec.method_name}'.")

        # 5) Optional sanity: index setting 'knn' should be true
        try:
            settings = self._client.indices.get_settings(index=self._index)
            knn_enabled = _safe_get(settings, [self._index, "settings", "index", "knn"])
            if str(knn_enabled).lower() not in {"true", "1"}:
                problems.append("- Index setting 'index.knn' is not enabled (should be true).")
        except Exception as e:
            logger.warning("Could not check index.knn setting: %s", e)

        metadata_props = _safe_get(m, ["properties", "metadata", "properties"], {}) or {}
        missing_metadata_fields = [field for field in REQUIRED_METADATA_FIELDS if field not in metadata_props]
        if missing_metadata_fields:
            logger.critical(
                "[VECTOR][OPENSEARCH][MAPPING] index %s missing metadata keyword fields %s required for session/attachment filters",
                self._index,
                missing_metadata_fields,
            )
            if allow_metadata_mapping_update and self._apply_metadata_mapping_updates(missing_metadata_fields):
                self._validate_index_compatibility(expected_dim, allow_metadata_mapping_update=False)
                return
            problems.append(f"- Missing metadata fields {', '.join(missing_metadata_fields)}. These fields must be mapped as keywords for session-scoped searches.")

        try:
            tag_field = metadata_props.get("tag_ids")
            if tag_field is None:
                problems.append("- Missing field 'metadata.tag_ids'. Fred relies on this keyword field for library filters.")
            else:
                tag_type = str(tag_field.get("type", "")).lower()
                subfields = tag_field.get("fields") or {}

                # Legacy buggy pattern: text + keyword subfield
                if tag_type == "text" and "keyword" in subfields:
                    problems.append(
                        "- 'metadata.tag_ids' is mapped as text+keyword. "
                        "Fred expects a pure 'keyword' field to avoid silent zero-hit filters. "
                        '💡 Fix: reindex with \'metadata.tag_ids\': {"type": "keyword"}.'
                    )
                elif tag_type != "keyword":
                    problems.append(f"- 'metadata.tag_ids' has unsupported type '{tag_type}'. Fred expects 'keyword' so that UUID filters are exact and predictable.")
        except Exception as e:
            # If this introspection itself fails, treat it as a hard problem:
            problems.append(f"- Could not inspect 'metadata.tag_ids' mapping (error: {e}). Fred requires this field as 'keyword' for tag/library filters.")

        if problems:
            raise ValueError(
                "OpenSearch index is not compatible with the configured embedding model.\n"
                f"   Index: {self._index}\n"
                f"   Model: {model_name}\n"
                "   Problems:\n" + "\n".join(f"   {p}" for p in problems) + "\n\n✔ Expected vector_field.method:\n"
                f"   engine={spec.engine}, space_type={spec.space_type}, name={spec.method_name}, dimension={spec.dim}\n"
                "Fix: recreate the index with the correct index mappin"
            )
        if warnings:
            for w in warnings:
                logger.warning("[VECTOR][OPENSEARCH] %s", w)
            logger.warning(
                "[VECTOR][OPENSEARCH] index mapping accepted with warnings: engine=%s space=%s method=%s dim=%s",
                method_engine,
                method_space,
                method_name,
                actual_dim,
            )
        else:
            logger.info("[VECTOR][OPENSEARCH] index mapping compatible: engine=%s space=%s method=%s dim=%s", method_engine, method_space, method_name, actual_dim)

    # --- helper: return a flat list of term filters (or None) ---
    def _to_filter_clause(self, f: Optional[SearchFilter]) -> Optional[List[Dict]]:
        """
        Fred rationale:
        - LangChain's OpenSearchVectorSearch expects `boolean_filter` to be a LIST of filters.
        - Our raw OS queries also expect that list under `bool.filter`.
        - Returning a dict with `bool.filter` here causes double nesting upstream.

        Backward compatibility:
        - For the special field `retrievable=True`, we include documents where the
          field is missing as well. This keeps older indices (that don't yet store
          `metadata.retrievable`) searchable until re-indexing occurs.
        """
        if not f:
            return None
        filters: List[Dict] = []
        if f.tag_ids:
            filters.append({"terms": {"metadata.tag_ids": list(f.tag_ids)}})
        if f.metadata_terms:
            for field, values in f.metadata_terms.items():
                meta_field = f"metadata.{field}"
                try:
                    values_list = list(values) if values is not None else []
                except TypeError:
                    values_list = [values]

                if field == "retrievable":
                    want_true = any(_is_true_value(v) for v in values_list)
                    want_false = any(_is_false_value(v) for v in values_list)
                    if not (want_true or want_false):
                        continue

                    logger.debug(
                        "[VECTOR][OPENSEARCH][FILTER] building retrievable filter: field=%s values=%s want_true=%s want_false=%s",
                        meta_field,
                        values_list,
                        want_true,
                        want_false,
                    )

                    def _retrievable_clause(value: bool) -> Dict:
                        # Accept missing field for backward compatibility with legacy indices.
                        return {
                            "bool": {
                                "should": [
                                    {"terms": {meta_field: [value]}},
                                    {"bool": {"must_not": {"exists": {"field": meta_field}}}},
                                ],
                                "minimum_should_match": 1,
                            }
                        }

                    if want_true and want_false:
                        filters.append(
                            {
                                "bool": {
                                    "should": [
                                        _retrievable_clause(True),
                                        _retrievable_clause(False),
                                    ],
                                    "minimum_should_match": 1,
                                }
                            }
                        )
                    elif want_true:
                        filters.append(_retrievable_clause(True))
                    elif want_false:
                        filters.append(_retrievable_clause(False))
                else:
                    include_values: List[Any] = []
                    exclude_values: List[Any] = []
                    for v in values_list:
                        if isinstance(v, str) and v.startswith("!"):
                            if v[1:]:
                                exclude_values.append(v[1:])
                        else:
                            include_values.append(v)
                    if include_values:
                        logger.debug(
                            "[VECTOR][OPENSEARCH][FILTER] adding terms filter: field=%s values=%s",
                            meta_field,
                            include_values,
                        )
                        filters.append({"terms": {meta_field: include_values}})
                    if exclude_values:
                        logger.debug(
                            "[VECTOR][OPENSEARCH][FILTER] adding must_not terms: field=%s values=%s",
                            meta_field,
                            exclude_values,
                        )
                        filters.append({"bool": {"must_not": {"terms": {meta_field: exclude_values}}}})
        if filters:
            logger.debug("[VECTOR][OPENSEARCH][FILTER] final filter list=%s", filters)
        return filters or None
