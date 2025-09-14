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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from langchain.schema.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch

from app.common.utils import get_embedding_model_name
from app.core.stores.vector.base_embedding_model import BaseEmbeddingModel
from app.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, AnnHit, BaseVectorStore, LexicalHit, LexicalSearchable, SearchFilter 

logger = logging.getLogger(__name__)


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
        embedding_model: BaseEmbeddingModel,
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

        self._vs: OpenSearchVectorSearch | None = None
        self._expected_dim: int | None = None

        logger.info(
            "🔗 OpenSearchVectorStoreAdapter initialized index=%r host=%r bulk=%s",
            self._index, self._host, self._bulk_size
        )

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
            self._check_vector_index_dimension(self._expected_dim)
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
            model_name = get_embedding_model_name(self._embedding_model)
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

    def ann_search(self, query: str, *, k: int, search_filter: Optional[SearchFilter] = None) -> List[AnnHit]:
        """
        ANN (semantic) search honoring library/document filters.
        Returns hydrated Documents with cosine similarity scores.
        """
        boolean_filter = self._to_filter_clause(search_filter)
        kwargs: Dict = {"boolean_filter": boolean_filter} if boolean_filter else {}

        pairs = self._lc.similarity_search_with_score(query, k=k, **kwargs)

        hits: List[AnnHit] = []
        model_name = get_embedding_model_name(self._embedding_model)
        now_iso = datetime.now(timezone.utc).isoformat()

        for rank, (doc, score) in enumerate(pairs, start=1):
            cid = doc.metadata.get(CHUNK_ID_FIELD) or doc.metadata.get("_id")
            if cid and CHUNK_ID_FIELD not in doc.metadata:
                doc.metadata[CHUNK_ID_FIELD] = cid
            # enrich for UI/telemetry
            doc.metadata["score"] = score
            doc.metadata["rank"] = rank
            doc.metadata["retrieved_at"] = now_iso
            doc.metadata.setdefault("embedding_model", model_name)
            doc.metadata.setdefault("vector_index", self._index)
            doc.metadata.setdefault("token_count", len((doc.page_content or "").split()))
            hits.append(AnnHit(document=doc, score=float(score)))

        return hits

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
        f = self._to_filter_clause(search_filter)
        body = {
            "size": k,
            "query": {
                "bool": {
                    "must": [{"match": {"text": {"query": query, "operator": "AND" if operator_and else "OR"}}}],
                    "filter": f["bool"]["filter"] if f else [],
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
        f = self._to_filter_clause(search_filter)
        body = {
            "size": k,
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                    "filter": f["bool"]["filter"] if f else [],
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

    def _check_vector_index_dimension(self, expected_dim: int):
        try:
            mapping = self._client.indices.get_mapping(index=self._index)
            actual_dim = mapping[self._index]["mappings"]["properties"]["vector_field"]["dimension"]
        except Exception as e:
            logger.warning("⚠️ Failed to check vector dimension: %s", e)
            return

        model_name = get_embedding_model_name(self._embedding_model)
        if actual_dim != expected_dim:
            raise ValueError(
                "❌ Vector dimension mismatch:\n"
                f"   - OpenSearch index '{self._index}' expects: {actual_dim}\n"
                f"   - Embedding model '{model_name}' outputs: {expected_dim}\n"
                "💡 Make sure the index and embedding model are compatible."
            )
        logger.info("✅ Vector dimension check passed: model %r outputs %s", model_name, expected_dim)

    def _to_filter_clause(self, f: Optional[SearchFilter]) -> Optional[Dict]:
        if not f:
            return None
        filters: List[Dict] = []
        if f.tag_ids:
            filters.append({"terms": {"metadata.tag_ids": list(f.tag_ids)}})
        if f.metadata_terms:
            for field, values in f.metadata_terms.items():
                filters.append({"terms": {f"metadata.{field}": list(values)}})
        return {"bool": {"filter": filters}} if filters else None
