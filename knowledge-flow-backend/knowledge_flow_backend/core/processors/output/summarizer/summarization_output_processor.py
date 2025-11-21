import logging
from typing import List, Optional, override

from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocSummary, DocumentMetadata
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor
from knowledge_flow_backend.core.processors.output.summarizer.smart_llm_summarizer import SmartDocSummarizer
from knowledge_flow_backend.core.processors.output.vectorization_processor.vectorization_utils import (
    load_langchain_doc_from_metadata,
)

logger = logging.getLogger(__name__)


class SummarizationOutputProcessor(BaseOutputProcessor):
    """
    Output processor that computes a document-level summary and keywords.

    It reuses the SmartDocSummarizer used by the vectorization pipeline, but
    exposes summarization as an explicit step in the processing pipeline so that
    admins can control when it runs.
    """

    def __init__(self) -> None:
        self.context = ApplicationContext.get_instance()
        self.splitter = self.context.get_text_splitter()
        self.smart_summarizer = SmartDocSummarizer(
            model_config=self.context.configuration.chat_model,
            splitter=self.splitter,
            opts={
                "sum_enabled": True,
                "sum_input_cap": 120_000,
                "sum_abs_words": 180,
                "sum_kw_top_k": 24,
                "mr_top_shards": 24,
                "mr_shard_words": 80,
                "small_threshold": 50_000,
                "large_threshold": 1_200_000,
            },
        )

    @override
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        try:
            document: Document = load_langchain_doc_from_metadata(file_path, metadata)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Summarization: failed to load document for %s: %s", metadata.document_uid, exc)
            return metadata

        if not document or not document.page_content:
            logger.info("Summarization: empty document content for %s; skipping.", metadata.document_uid)
            return metadata

        try:
            abstract: Optional[str]
            keywords: Optional[List[str]]
            abstract, keywords = self.smart_summarizer.summarize_document(document)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Summarization: summarizer failed for %s: %s", metadata.document_uid, exc)
            return metadata

        if abstract or keywords:
            logger.info(
                "Summarization: computed summary for %s (abstract_len=%d, keywords=%d)",
                metadata.document_uid,
                len(abstract or ""),
                len(keywords or []),
            )
            metadata.summary = DocSummary(
                abstract=abstract,
                keywords=keywords or [],
                model_name=self.smart_summarizer.get_model_name(),
                method="SmartDocSummarizer@v1",
            )

        return metadata

