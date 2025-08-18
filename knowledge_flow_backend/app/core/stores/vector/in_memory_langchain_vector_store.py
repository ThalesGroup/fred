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

from langchain.embeddings.base import Embeddings
from langchain.schema.document import Document
from langchain_core.vectorstores import InMemoryVectorStore

from app.common.utils import get_embedding_model_name
from app.core.stores.vector.base_vector_store import BaseVectoreStore

logger = logging.getLogger(__name__)


class InMemoryLangchainVectorStore(BaseVectoreStore):
    """
    In-Memory langchain Vector Store.
    -------------------
    A simple and minimalistic in-memory vector store.
    It uses the langchain_community FAISS class.
    """

    def __init__(self, embedding_model: Embeddings):
        """
        Args:
            embedding_model (Embeddings): The embedding model to use for vectorization.
        """
        self.embedding_model = embedding_model
        self.vectorstore = InMemoryVectorStore(embedding=embedding_model)

    def add_documents(self, documents: List[Document]) -> None:
        """
        Add raw documents to the in-memory vector store.
        Embeddings will be computed internally by LangChain using the configured embedding model.
        Args:
            documents (List[Document]): List of documents to embed and store.
        """
        self.vectorstore.add_documents(documents)
        logger.info("✅ Documents added successfully to in memory store.")
        top_n = 3
        for index, (id, doc) in enumerate(self.vectorstore.store.items()):
            if index < top_n:
                # docs have keys 'id', 'vector', 'text', 'metadata'
                logger.debug(f"{id}: {doc['text']}")
            else:
                break

    def similarity_search_with_score(self, query: str, k: int = 5, documents_ids: Iterable[str] | None = None) -> List[Tuple[Document, float]]:
        if documents_ids:
            # Check if a document uid is in valid documents_ids list
            def tag_filter(doc: Document) -> bool:
                doc_uid = doc.metadata.get("document_uid")
                if doc_uid is None:
                    return False
                return doc_uid in documents_ids

            results = self.vectorstore.similarity_search_with_score(query, k=k, filter=tag_filter)
        else:
            results = self.vectorstore.similarity_search_with_score(query, k=k)

        enriched = []

        for rank, (doc, score) in enumerate(results):
            doc.metadata["score"] = score
            doc.metadata["rank"] = rank
            doc.metadata["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            doc.metadata["embedding_model"] = get_embedding_model_name(self.embedding_model)
            doc.metadata["vector_index"] = "in-memory"
            doc.metadata["token_count"] = len(doc.page_content.split())  # crude estimate
            enriched.append((doc, score))

        return enriched

    def delete_vectors(self, document_uid: str) -> None:
        """Delete the vectors associated with a document."""
        pass
