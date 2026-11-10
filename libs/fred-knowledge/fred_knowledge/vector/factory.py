# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import logging
from uuid import UUID

from langchain_core.embeddings import Embeddings

from fred_knowledge.configuration import OpenSearchVectorIndexConfig, PgVectorStorageConfig
from fred_knowledge.text.base_text_splitter import BaseTextSplitter
from fred_knowledge.vector.base_vector_store import BaseVectorStore
from fred_knowledge.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from fred_knowledge.vector.pgvector_store import PgVectorStoreAdapter

logger = logging.getLogger(__name__)


def corpus_index(base: str, organization_id: UUID) -> str:
    """One index per organization: its vectors share the organization's embedding model."""
    return f"{base}-{organization_id}"


def build_vector_store(
    embedding_model: Embeddings | None,
    store,
    *,
    organization_id: UUID,
    embedding_model_name: str,
    opensearch_config,
    postgres_config,
    kpi,
    splitter: BaseTextSplitter,
    read_only: bool = False,
) -> BaseVectorStore:
    """Construct one organization's corpus store for the API or a processing attempt.

    Without an embedding model, the store only deletes or flags existing vectors."""

    if isinstance(store, OpenSearchVectorIndexConfig):
        if not opensearch_config:
            raise ValueError("Missing OpenSearch configuration")
        password = opensearch_config.password
        if not password:
            raise ValueError("Missing OpenSearch credentials: OPENSEARCH_PASSWORD")

        instance = OpenSearchVectorStoreAdapter(
            embedding_model=embedding_model,
            embedding_model_name=embedding_model_name,
            kpi=kpi,
            host=opensearch_config.host,
            index=corpus_index(store.index, organization_id),
            username=opensearch_config.username,
            password=password,
            secure=opensearch_config.secure,
            verify_certs=opensearch_config.verify_certs,
            bulk_size=store.bulk_size,
            read_only=read_only,
            splitter=splitter,
        )
        return instance
    elif isinstance(store, PgVectorStorageConfig):
        if embedding_model is None:
            raise ValueError("A pgvector corpus requires its embedding model")
        pg = postgres_config
        collection = corpus_index(store.collection_name, organization_id)
        instance = PgVectorStoreAdapter(
            embedding_model=embedding_model,
            embedding_model_name=embedding_model_name,
            postgres_config=pg,
            collection_name=collection,
        )
        logger.info("Using postgres collection=%s (default table)", collection)
    else:
        raise ValueError("Unsupported vector store backend")
    return instance
