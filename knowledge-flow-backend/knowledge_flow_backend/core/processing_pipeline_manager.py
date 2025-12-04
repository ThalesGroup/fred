import logging
from dataclasses import dataclass, field
from typing import Dict, List

from knowledge_flow_backend.application_context import ApplicationContext
from fred_core.processors import DocumentMetadata
from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline

logger = logging.getLogger(__name__)


@dataclass
class ProcessingPipelineManager:
    """
    Registry for library-aware pipelines.

    This manager owns:
      - a default pipeline (mirroring legacy behaviour),
      - an optional set of named pipelines,
      - a mapping from tag_id -> pipeline_name.

    For now, only the default pipeline is instantiated. Tag-based routing is
    prepared but no tag is mapped yet; all documents go through the default
    pipeline. Admin APIs can later populate tag_to_pipeline and pipelines.
    """

    default_pipeline: ProcessingPipeline
    pipelines: Dict[str, ProcessingPipeline] = field(default_factory=dict)
    tag_to_pipeline: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def create_with_default(cls, context: ApplicationContext) -> "ProcessingPipelineManager":
        default = ProcessingPipeline.build_default(context)
        pipelines = {"default": default}
        return cls(default_pipeline=default, pipelines=pipelines)

    def get_pipeline_for_metadata(self, metadata: DocumentMetadata) -> ProcessingPipeline:
        """
        Select a pipeline based on the document's library tags.

        Current heuristic:
        - Iterate metadata.tags.tag_ids in order.
        - If a tag id is mapped to a pipeline name, and that pipeline exists,
          return it.
        - Otherwise, fall back to the default pipeline.
        """
        tag_ids: List[str] = metadata.tags.tag_ids or []

        for tag_id in tag_ids:
            pipeline_name = self.tag_to_pipeline.get(tag_id)
            if pipeline_name:
                pipeline = self.pipelines.get(pipeline_name)
                if pipeline:
                    return pipeline

        return self.default_pipeline
