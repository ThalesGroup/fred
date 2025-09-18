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
from typing import Iterable, List, Optional, Tuple

import weaviate
from langchain.embeddings.base import Embeddings
from langchain.schema.document import Document
from langchain_community.vectorstores import Weaviate

from app.core.stores.vector.base_vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


class WeaviateVectorStore(BaseVectorStore):
    def __init__(
        self,
        embedding_model: Embeddings,
        embedding_model_name: str,
        host: str,
        index_name: str = "CodeDocuments",
        text_key: str = "content",
    ):
        self.embedding_model = embedding_model
        self.embedding_model_name = embedding_model_name
        self.index_name = index_name
        self.text_key = text_key
        self.client = weaviate.Client(host)  # v3 syntax

        if not self.client.is_ready():
            raise RuntimeError(f"Weaviate at {host} is not ready.")

        self.vectorstore = Weaviate(
            client=self.client,
            index_name=self.index_name,
            text_key=self.text_key,
            embedding=self.embedding_model,
            by_text=False,  # We handle embedding ourselves
        )

        logger.info(f"✅ Weaviate vector store initialized on {host} (index: {index_name})")

    def add_documents(self, documents: List[Document], *, ids: Optional[List[str]] = None) -> List[str]:
        self.vectorstore.add_documents(documents)
        logger.info(f"✅ Added {len(documents)} documents to Weaviate.")
        return ids or []

    def similarity_search_with_score(self, query: str, k: int = 5, documents_ids: Iterable[str] | None = None) -> List[Tuple[Document, float]]:
        if documents_ids:
            # Weaviate where filter to check if document uid is in valid documents_ids list
            where_filter = {"operator": "Or", "operands": [{"path": ["metadata", "document_uid"], "operator": "ContainsAny", "valueText": documents_ids}]}
            results = self.vectorstore.similarity_search_with_score(query, k=k, where_filter=where_filter)
        else:
            results = self.vectorstore.similarity_search_with_score(query, k=k)

        enriched = []

        for rank, (doc, score) in enumerate(results):
            doc.metadata["score"] = score
            doc.metadata["rank"] = rank
            doc.metadata["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            doc.metadata["embedding_model"] = self.embedding_model_name or "unknown"
            doc.metadata["vector_index"] = self.index_name
            doc.metadata["token_count"] = len(doc.page_content.split())
            enriched.append((doc, score))

        return enriched

    def close(self):
        try:
            self.client.close()
            logger.info("🔒 Closed Weaviate connection cleanly.")
        except Exception as e:
            logger.warning(f"⚠️ Failed to close Weaviate client: {e}")
