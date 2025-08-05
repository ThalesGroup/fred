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
from typing import Iterable, List, Tuple

from langchain.schema.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch

from app.common.utils import get_embedding_model_name
from app.core.stores.vector.base_vector_store import BaseEmbeddingModel, BaseVectoreStore

logger = logging.getLogger(__name__)


class OpenSearchVectorStoreAdapter(BaseVectoreStore):
    def __init__(
        self,
        embedding_model: BaseEmbeddingModel,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.vector_index = index
        self.embedding_model = embedding_model
        self.host = host
        self.username = username
        self.password = password
        self.secure = secure
        self.verify_certs = verify_certs

        self._opensearch_vector_search: OpenSearchVectorSearch | None = None
        self._expected_dim: int | None = None

    @property
    def opensearch_vector_search(self) -> OpenSearchVectorSearch:
        if self._opensearch_vector_search is None:
            self._opensearch_vector_search = OpenSearchVectorSearch(
                opensearch_url=self.host,
                index_name=self.vector_index,
                embedding_function=self.embedding_model,
                use_ssl=self.secure,
                verify_certs=self.verify_certs,
                http_auth=(self.username, self.password),
            )

            self._expected_dim = self._get_embedding_dimension()
            self._check_vector_index_dimension(self._expected_dim)

        return self._opensearch_vector_search

    def _check_vector_index_dimension(self, expected_dim: int):
        try:
            mapping = self.opensearch_vector_search.client.indices.get_mapping(index=self.vector_index)
            actual_dim = mapping[self.vector_index]["mappings"]["properties"]["vector_field"]["dimension"]
        except Exception as e:
            logger.warning(f"⚠️ Failed to check vector dimension: {e}")
            return

        model_name = get_embedding_model_name(self.embedding_model)

        if actual_dim != expected_dim:
            raise ValueError(
                f"❌ Vector dimension mismatch:\n"
                f"   - OpenSearch index '{self.vector_index}' expects: {actual_dim}\n"
                f"   - Embedding model '{model_name}' outputs: {expected_dim}\n"
                f"💡 Make sure the index and embedding model are compatible."
            )
        logger.info(f"✅ Vector dimension check passed: model '{model_name}' outputs {expected_dim}")

    def _get_embedding_dimension(self) -> int:
        dummy_vector = self.embedding_model.embed_query("dummy")
        return len(dummy_vector)

    def add_documents(self, documents: List[Document]) -> None:
        try:
            self.opensearch_vector_search.add_documents(documents)
            logger.info("✅ Documents added successfully.")
        except Exception as e:
            logger.exception("❌ Failed to add documents to OpenSearch.")
            raise RuntimeError("Unexpected error during vector indexing.") from e

    def similarity_search_with_score(
        self, query: str, k: int = 5, documents_ids: Iterable[str] | None = None
    ) -> List[Tuple[Document, float]]:
        if documents_ids:
            boolean_filter = {"terms": {"metadata.document_uid": list(documents_ids)}}
            logger.debug("Using boolean_filter with vector search: %s", boolean_filter)
            results = self.opensearch_vector_search.similarity_search_with_score(query, k=k, boolean_filter=boolean_filter)
        else:
            logger.debug("No boolean_filter with vector search")
            results = self.opensearch_vector_search.similarity_search_with_score(query, k=k)

        enriched = []

        for rank, (doc, score) in enumerate(results):
            doc.metadata["score"] = score
            doc.metadata["rank"] = rank
            doc.metadata["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            doc.metadata["embedding_model"] = get_embedding_model_name(self.embedding_model)
            doc.metadata["vector_index"] = self.vector_index
            doc.metadata["token_count"] = len(doc.page_content.split())
            enriched.append((doc, score))

        return enriched
