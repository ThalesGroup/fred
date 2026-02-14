import logging
from dataclasses import dataclass, field
from typing import Dict, List

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseInputProcessor

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
    default_profile: IngestionProcessingProfile = IngestionProcessingProfile.MEDIUM
    pipelines: Dict[str, ProcessingPipeline] = field(default_factory=dict)
    tag_to_pipeline: Dict[str, str] = field(default_factory=dict)
    profile_to_pipeline: Dict[IngestionProcessingProfile, str] = field(default_factory=dict)

    @classmethod
    def create_with_default(cls, context: ApplicationContext) -> "ProcessingPipelineManager":
        default = ProcessingPipeline.build_default(context)
        pipelines = {"default": default}
        manager = cls(
            default_pipeline=default,
            default_profile=context.get_config().processing.default_profile,
            pipelines=pipelines,
        )
        manager._register_profile_pipelines(context)
        return manager

    @staticmethod
    def _instantiate_input_processor(class_path: str) -> BaseInputProcessor:
        module_path, class_name = class_path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        cls_ref = getattr(module, class_name)
        instance = cls_ref()
        if not isinstance(instance, BaseInputProcessor):
            raise TypeError(f"{class_path} is not a BaseInputProcessor")
        return instance

    @staticmethod
    def _clone_pipeline(template: ProcessingPipeline, name: str) -> ProcessingPipeline:
        input_processors = {ext: proc.__class__() for ext, proc in template.input_processors.items()}
        output_processors = {ext: [proc.__class__() for proc in processors] for ext, processors in template.output_processors.items()}
        library_output_processors = [proc.__class__() for proc in template.library_output_processors]
        return ProcessingPipeline(
            name=name,
            input_processors=input_processors,
            output_processors=output_processors,
            library_output_processors=library_output_processors,
        )

    def _register_profile_pipelines(self, context: ApplicationContext) -> None:
        processing_cfg = context.get_config().processing
        profile_cfg_by_name = {
            IngestionProcessingProfile.FAST: processing_cfg.profiles.fast,
            IngestionProcessingProfile.MEDIUM: processing_cfg.profiles.medium,
            IngestionProcessingProfile.RICH: processing_cfg.profiles.rich,
        }

        for profile, profile_cfg in profile_cfg_by_name.items():
            pipeline_name = f"profile-{profile.value}"
            pipeline = self._clone_pipeline(self.default_pipeline, pipeline_name)
            selected_processors: List[ProcessingConfig.ProfileInputProcessorConfig] = profile_cfg.input_processors or []

            # Profile input processors are explicit; do not keep hidden inherited entries.
            pipeline.input_processors = {}
            for entry in selected_processors:
                pipeline.input_processors[entry.suffix.lower()] = self._instantiate_input_processor(entry.class_path)

            self.pipelines[pipeline_name] = pipeline
            self.profile_to_pipeline[profile] = pipeline_name

    @staticmethod
    def normalize_profile(profile: IngestionProcessingProfile | str | None) -> IngestionProcessingProfile | None:
        if profile is None:
            return None
        if isinstance(profile, IngestionProcessingProfile):
            return profile
        return IngestionProcessingProfile(profile)

    def get_pipeline_for_profile(self, profile: IngestionProcessingProfile | str | None) -> ProcessingPipeline:
        normalized = self.normalize_profile(profile) or self.default_profile
        pipeline_name = self.profile_to_pipeline.get(normalized, "default")
        return self.pipelines.get(pipeline_name, self.default_pipeline)

    def get_pipeline_for_metadata(self, metadata: DocumentMetadata, profile: IngestionProcessingProfile | str | None = None) -> ProcessingPipeline:
        """
        Select a pipeline based on the document's library tags.

        Current heuristic:
        - If a profile is explicitly requested, use the profile pipeline first.
        - Iterate metadata.tags.tag_ids in order.
        - If a tag id is mapped to a pipeline name, and that pipeline exists,
          return it.
        - Otherwise, fall back to the default pipeline.
        """
        normalized = self.normalize_profile(profile) or self.default_profile
        pipeline_name = self.profile_to_pipeline.get(normalized, "default")
        pipeline = self.pipelines.get(pipeline_name)
        if pipeline is not None:
            return pipeline

        tag_ids: List[str] = metadata.tags.tag_ids or []

        for tag_id in tag_ids:
            pipeline_name = self.tag_to_pipeline.get(tag_id)
            if pipeline_name:
                pipeline = self.pipelines.get(pipeline_name)
                if pipeline:
                    return pipeline

        return self.default_pipeline
