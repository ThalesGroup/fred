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
from typing import Dict, List, Optional, Sequence

from langchain.schema.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_core.embeddings import Embeddings

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, AnnHit, BaseVectorStore, LexicalHit, LexicalSearchable, SearchFilter

logger = logging.getLogger(__name__)


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


class OpenSearchVectorStoreAdapter(BaseVectorStore, LexicalSearchable):
    """
    Fred — OpenSearch-backed Vector Store (LangChain for ANN + OS client for lexical/phrase).

    Why this shape:
      - Matches the minimal BaseVectorStore contract (ingest + ANN).
      - Implements LexicalSearchable so 'hybrid' and 'strict' retrievers can use BM25/phrase.
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

        logger.info("🔗 OpenSearchVectorStoreAdapter initialized index=%r host=%r bulk=%s", self._index, self._host, self._bulk_size)

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
                bulk_size=self._bulk_size,
            )
            self._expected_dim = self._get_embedding_dimension()
            self._validate_index_compatibility(self._expected_dim)
        return self._vs

    @property
    def _client(self):
        # low-level OpenSearch client for BM25/phrase
        return self._lc.client

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

            logger.info("✅ Upserted %s chunk(s) into %s", len(assigned_ids), self._index)
            return assigned_ids

        except Exception as e:
            logger.exception("❌ Failed to add documents to OpenSearch.")
            raise RuntimeError("Unexpected error during vector indexing.") from e

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        try:
            body = {"query": {"term": {"metadata.document_uid": {"value": document_uid}}}}
            resp = self._client.delete_by_query(index=self._index, body=body)
            deleted = int(resp.get("deleted", 0))
            logger.info("✅ Deleted %s vector chunks for document_uid=%s.", deleted, document_uid)
        except Exception:
            logger.exception("❌ Failed to delete vectors for document_uid=%s.", document_uid)
            raise RuntimeError("Failed to delete vectors from OpenSearch.")

    # ---------- BaseVectorStore: ANN (semantic) ----------
    def _supports_knn_filter(self) -> bool:
        """Detect if OpenSearch supports knn.filter (>=2.19). Cached after first check."""
        if hasattr(self, "_knn_filter_supported"):
            return self._knn_filter_supported

        try:
            info = self._client.info()
            version = info.get("version", {}).get("number", "")
            major, minor, *_ = (int(x) for x in version.split("."))
            self._knn_filter_supported = (major, minor) >= (2, 19)
        except Exception:
            logger.warning("⚠️ Could not determine OpenSearch version; assuming no knn.filter support.")
            self._knn_filter_supported = False

        return self._knn_filter_supported

    # --- ann_search: keep passing the list directly to boolean_filter ---
    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """
        ANN (semantic) search compatible with OpenSearch 2.18 and 2.19+.
        Tries native knn.filter (2.19+) → falls back to bool+knn (2.18) → LangChain wrapper.
        """

        filters = self._to_filter_clause(search_filter)
        now_iso = datetime.now(timezone.utc).isoformat()
        model_name = self._embedding_model_name or "unknown"

        # ---- helpers ----------------------------------------------------------

        def _build_ann_hits(hits_data: list) -> List[AnnHit]:
            """Normalize OpenSearch hit results into AnnHit list."""
            results: List[AnnHit] = []
            for rank, h in enumerate(hits_data, start=1):
                src = h.get("_source", {})
                meta = src.get("metadata", {})
                text = src.get("text", "")
                cid = meta.get(CHUNK_ID_FIELD) or h.get("_id")
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
                results.append(AnnHit(document=doc, score=float(h.get("_score", 0.0))))
            return results

        def _try_os_query(body: dict, label: str) -> Optional[List[AnnHit]]:
            """Run a raw OpenSearch query. Returns hits or None if it failed."""
            try:
                res = self._client.search(index=self._index, body=body)
                hits_data = res.get("hits", {}).get("hits", [])
                logger.info("✅ ANN search (%s) returned %d hits", label, len(hits_data))
                return _build_ann_hits(hits_data)
            except Exception as e:
                logger.debug("⚠️ %s query failed: %s", label, e)
                return None

        # ---- step 1: embed query ---------------------------------------------

        try:
            vector = self._embedding_model.embed_query(query)
        except Exception as e:
            logger.exception("❌ Failed to compute embedding.")
            raise RuntimeError("Embedding model failed.") from e

        # ---- step 2: native knn.filter (2.19+) -------------------------------

        if self._supports_knn_filter():
            knn_body = {
                "size": k,
                "query": {"knn": {"vector_field": {"vector": vector, "k": k}}},
                "_source": True,
            }
            if filters:
                knn_body["query"]["knn"]["vector_field"]["filter"] = {"bool": {"filter": filters}}
            hits = _try_os_query(knn_body, "native knn.filter")
            if hits is not None:
                return hits
        else:
            logger.debug("ℹ️ knn.filter not supported on this OpenSearch version — using bool+knn fallback.")

        # ---- step 3: bool + knn fallback (2.18 and below) --------------------

        bool_knn_body = {
            "size": k,
            "query": {
                "bool": {
                    "filter": filters or [],
                    "must": [{"knn": {"vector_field": {"vector": vector, "k": k}}}],
                }
            },
            "_source": True,
        }

        hits = _try_os_query(bool_knn_body, "bool+knn fallback")
        if hits is not None:
            return hits

        # ---- step 4: LangChain fallback --------------------------------------

        try:
            # No filters → simple call
            if not filters:
                pairs = self._lc.similarity_search_with_score(query, k=k)
            else:
                in_query_filter = {"bool": {"filter": filters}}

                # Try known filter argument names in order
                for attempt in ("efficient_filter", "filter", "boolean_filter"):
                    try:
                        if attempt == "efficient_filter":
                            pairs = self._lc.similarity_search_with_score(query, k=k, efficient_filter=in_query_filter)
                        elif attempt == "filter":
                            pairs = self._lc.similarity_search_with_score(query, k=k, filter=in_query_filter)
                        else:  # boolean_filter
                            pairs = self._lc.similarity_search_with_score(query, k=k, boolean_filter=filters)
                        break  # success → exit loop
                    except TypeError:
                        continue
                else:
                    # No argument worked
                    raise TypeError("No compatible filter argument found in LangChain OpenSearchVectorSearch.")
        except Exception:
            logger.exception("❌ LangChain ANN search failed.")
            raise RuntimeError("All ANN search modes failed.")

        # normalize LC results
        results: List[AnnHit] = []
        for rank, (doc, score) in enumerate(pairs, start=1):
            cid = doc.metadata.get(CHUNK_ID_FIELD) or doc.metadata.get("_id")
            doc.metadata.update(
                {
                    CHUNK_ID_FIELD: cid,
                    "score": float(score),
                    "rank": rank,
                    "retrieved_at": now_iso,
                    "embedding_model": model_name,
                    "vector_index": self._index,
                    "token_count": len((doc.page_content or "").split()),
                }
            )
            results.append(AnnHit(document=doc, score=float(score)))

        logger.info("✅ ANN search (LangChain fallback) returned %d hits", len(results))
        return results

    # ---------- LexicalSearchable capability ----------

    def lexical_search(
        self,
        query: str,
        *,
        k: int,
        search_filter: Optional[SearchFilter] = None,
        operator_and: bool = True,
    ) -> List[LexicalHit]:
        """
        BM25 search with same filter semantics; returns (chunk_id, score) only.
        """
        filters = self._to_filter_clause(search_filter)  # List[Dict] | None
        body = {
            "size": k,
            "query": {
                "bool": {
                    "must": [{"match": {"text": {"query": query, "operator": "AND" if operator_and else "OR"}}}],
                    "filter": filters or [],
                }
            },
            "_source": False,
        }
        res = self._client.search(index=self._index, body=body)
        return [LexicalHit(chunk_id=h["_id"], score=float(h["_score"])) for h in res.get("hits", {}).get("hits", [])]

    def phrase_search(
        self,
        phrase: str,
        *,
        fields: Sequence[str],
        k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[str]:
        """
        Exact phrase match across fields like text, metadata.section, metadata.title.
        Returns matching chunk ids.
        """
        should = [{"match_phrase": {field: {"query": phrase}}} for field in fields]
        filters = self._to_filter_clause(search_filter)  # List[Dict] | None
        body = {
            "size": k,
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                    "filter": filters or [],
                }
            },
            "_source": False,
        }
        res = self._client.search(index=self._index, body=body)
        return [h["_id"] for h in res.get("hits", {}).get("hits", [])]

    # ---------- helpers ----------

    def _get_embedding_dimension(self) -> int:
        dummy_vector = self._embedding_model.embed_query("dummy")
        return len(dummy_vector)

    def _validate_index_compatibility(self, expected_dim: int):
        """
        Fred rationale:
        - We fail fast if index mapping cannot faithfully serve the configured embedding model.
        - Checks: vector dimension, engine, space type, and HNSW method.
        """
        try:
            mapping = self._client.indices.get_mapping(index=self._index)
        except Exception as e:
            logger.warning("⚠️ Could not fetch mapping for %r: %s", self._index, e)
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

        # 1) Dimension
        if actual_dim != spec.dim:
            problems.append(f"- Dimension mismatch: index has {actual_dim}, model '{model_name}' requires {spec.dim}.")

        # 2) Engine (we standardize on lucene)
        if (method_engine or "") != spec.engine:
            problems.append(f"- Engine mismatch: index uses '{method_engine}', expected '{spec.engine}'. Lucene is recommended; nmslib may degrade recall and complicate filters.")

        # 3) Space type (cosine for OpenAI)
        if (method_space or "") != spec.space_type:
            msg = f"- Space mismatch: index uses '{method_space}', expected '{spec.space_type}' for OpenAI embeddings."
            if (method_space or "").lower() in {"l2", "euclidean"}:
                msg += " If you must keep L2, you must L2-normalize vectors at ingest and query time (not recommended)."
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
            logger.debug("Could not check index.knn setting: %s", e)

        if problems:
            raise ValueError(
                "❌ OpenSearch index is not compatible with the configured embedding model.\n"
                f"   Index: {self._index}\n"
                f"   Model: {model_name}\n"
                "   Problems:\n" + "\n".join(f"   {p}" for p in problems) + "\n\n✔ Expected vector_field.method:\n"
                f"   engine={spec.engine}, space_type={spec.space_type}, name={spec.method_name}, dimension={spec.dim}\n"
                "💡 Fix: recreate the index with lucene+cosinesimil (HNSW) and the correct dimension."
            )
        else:
            logger.info("✅ Index mapping is compatible: engine=%s space=%s method=%s dim=%s", method_engine, method_space, method_name, actual_dim)

    # --- helper: return a flat list of term filters (or None) ---
    def _to_filter_clause(self, f: Optional[SearchFilter]) -> Optional[List[Dict]]:
        """
        Fred rationale:
        - LangChain's OpenSearchVectorSearch expects `boolean_filter` to be a LIST of filters.
        - Our raw OS queries also expect that list under `bool.filter`.
        - Returning a dict with `bool.filter` here causes double nesting upstream.
        """
        if not f:
            return None
        filters: List[Dict] = []
        if f.tag_ids:
            filters.append({"terms": {"metadata.tag_ids": list(f.tag_ids)}})
        if f.metadata_terms:
            for field, values in f.metadata_terms.items():
                filters.append({"terms": {f"metadata.{field}": list(values)}})
        return filters or None
