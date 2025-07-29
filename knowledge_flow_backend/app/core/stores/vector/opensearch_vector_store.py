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

from datetime import datetime, timezone
import logging
from typing import List, Tuple
from langchain.schema.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch

from app.common.utils import get_embedding_model_name
from app.core.stores.vector.base_vector_store import BaseEmbeddingModel, BaseVectoreStore
logger = logging.getLogger(__name__)


class OpenSearchVectorStoreAdapter(BaseVectoreStore):
    """
    Opensearch Vector Store.

    -------------------
    1. This class is an adapter for OpenSearch vector store.
    2. It implements the VectorStoreInterface.
    3. It uses the langchain_community OpenSearchVectorSearch class.

    It accepts documents + embeddings and stores them into the configured OpenSearch vector index.
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
    ):
        self.vector_index = index
        self.opensearch_vector_search = OpenSearchVectorSearch(
            opensearch_url=host,
            index_name=index,
            embedding_function=embedding_model,
            use_ssl=secure,
            verify_certs=verify_certs,
            http_auth=(username, password),
        )
        expected_dim = self._get_embedding_dimension()
        self._check_vector_index_dimension(expected_dim)

    def _check_vector_index_dimension(self, expected_dim: int):
        mapping = self.opensearch_vector_search.client.indices.get_mapping(index=self.vector_index)
        actual_dim = mapping[self.vector_index]["mappings"]["properties"]["vector_field"]["dimension"]
        
        model_name = get_embedding_model_name(self.opensearch_vector_search.embedding_function)
        
        if actual_dim != expected_dim:
            raise ValueError(
                f"❌ Vector dimension mismatch:\n"
                f"   - OpenSearch index '{self.vector_index}' expects: {actual_dim}\n"
                f"   - Embedding model '{model_name}' outputs: {expected_dim}\n"
                f"💡 Make sure the index and embedding model are compatible."
            )
        logger.info(f"✅ Vector dimension check passed: model '{model_name}' outputs {expected_dim}")

    def _get_embedding_dimension(self) -> int:
        dummy_vector = self.opensearch_vector_search.embedding_function.embed_query("dummy")
        return len(dummy_vector)
    
    def add_documents(self, documents: List[Document]) -> None:
        """
        Add raw documents to OpenSearch.
        Embeddings will be computed internally by LangChain using the configured embedding model.

        Args:
            documents (List[Document]): List of documents to embed and store.
        """
        try:
            self.opensearch_vector_search.add_documents(documents)
            logger.info("✅ Documents added successfully.")
        except Exception as e:
            logger.exception("❌ Failed to add documents to OpenSearch.")
            raise RuntimeError("Unexpected error during vector indexing.") from e

    def similarity_search_with_score(self, query: str, k: int = 5) -> List[Tuple[Document, float]]:
        results = self.opensearch_vector_search.similarity_search_with_score(query, k=k)
        enriched = []

        for rank, (doc, score) in enumerate(results):
            doc.metadata["score"] = score
            doc.metadata["rank"] = rank
            doc.metadata["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            doc.metadata["embedding_model"] = get_embedding_model_name(self.opensearch_vector_search.embedding_function)
            doc.metadata["vector_index"] = self.vector_index
            doc.metadata["token_count"] = len(doc.page_content.split())  # simple estimation
            enriched.append((doc, score))

        return enriched
