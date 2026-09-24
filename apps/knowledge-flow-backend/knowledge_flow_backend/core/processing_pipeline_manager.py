# Copyright Thales 2026
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
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List

from fred_core.documents.document_structures import DocumentMetadata

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.processing_profile_context import coerce_processing_profile, processing_profile_scope
from knowledge_flow_backend.common.structures import IngestionProcessingProfile, ProcessingConfig
from knowledge_flow_backend.core.processing_pipeline import ProcessingPipeline
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseInputProcessor

logger = logging.getLogger(__name__)


@dataclass
class ProcessingPipelineManager:
    """Select extraction and output pipelines by processing profile."""

    default_pipeline: ProcessingPipeline
    default_profile: IngestionProcessingProfile = IngestionProcessingProfile.medium
    pipelines: Dict[str, ProcessingPipeline] = field(default_factory=dict)
    profile_to_pipeline: Dict[IngestionProcessingProfile, str] = field(default_factory=dict)

    @classmethod
    def create_with_default(cls, context: ApplicationContext, *, include_output: bool = True) -> "ProcessingPipelineManager":
        default = ProcessingPipeline.build_default(context, include_output=include_output)
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
        # Keep this clone lightweight: profile pipelines only need different input
        # mappings. Output processors and library processors are shared instances.
        input_processors = dict(template.input_processors)
        output_processors = {ext: list(processors) for ext, processors in template.output_processors.items()}
        library_output_processors = list(template.library_output_processors)
        return ProcessingPipeline(
            name=name,
            input_processors=input_processors,
            output_processors=output_processors,
            library_output_processors=library_output_processors,
        )

    def _register_profile_pipelines(self, context: ApplicationContext) -> None:
        processing_cfg = context.get_config().processing
        profile_cfg_by_name = {
            IngestionProcessingProfile.fast: processing_cfg.profiles.fast,
            IngestionProcessingProfile.medium: processing_cfg.profiles.medium,
            IngestionProcessingProfile.rich: processing_cfg.profiles.rich,
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

    def run_input(
        self,
        *,
        input_path: "pathlib.Path",
        output_dir: "pathlib.Path",
        metadata: DocumentMetadata,
        profile: IngestionProcessingProfile | str | None = None,
    ) -> None:
        """Run one document's extraction stage, writing its output into output_dir.

        The narrowest entry point into extraction: a pipeline manager needs the
        configuration and the processor classes. Extraction-only construction
        excludes output processors; input processors may still require stores.
        Both `IngestionService.process_input` and the extraction subprocess call
        this method, keeping the extraction algorithm shared.

        The profile scope is entered here, so the processors read the same
        effective per-profile settings on both paths.
        """
        normalized_profile = coerce_processing_profile(profile)
        with processing_profile_scope(normalized_profile):
            pipeline = self.get_pipeline_for_profile(normalized_profile)
            pipeline.process_input(input_path=input_path, output_dir=output_dir, metadata=metadata)

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
