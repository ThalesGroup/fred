from fred_core.store.vector_search import MARKDOWN_TABLE_CHUNK_KIND
from fred_knowledge.text.semantic_splitter import SemanticSplitter
from langchain_core.documents import Document


def test_table_chunk_kind_survives_metadata_sanitisation():
    """chunk_kind is the persisted vocabulary; the table_* keys are splitter-local."""
    from knowledge_flow_worker.core.processors.output.vectorization_processor.vectorization_utils import sanitize_chunk_metadata

    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    table = next(c for c in splitter.split(Document(page_content="| a | b |\n|---|---|\n| 1 | 2 |\n")) if c.metadata.get("chunk_kind") == MARKDOWN_TABLE_CHUNK_KIND)

    kept, _ = sanitize_chunk_metadata(table.metadata)

    assert kept.get("chunk_kind") == MARKDOWN_TABLE_CHUNK_KIND
