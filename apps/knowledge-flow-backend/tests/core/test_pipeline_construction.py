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

"""Extraction builds no output dependencies; ordinary pipelines retain them."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.core import processing_pipeline
from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager
from knowledge_flow_backend.core.processors.output.base_library_output_processor import LibraryOutputProcessor


class LibraryProcessor(LibraryOutputProcessor):
    constructed = 0

    def __init__(self):
        type(self).constructed += 1

    def process_library(self, documents, library_tag=None):
        return []


@pytest.mark.parametrize("include_output", [False, True])
def test_profile_construction_preserves_input_selection_without_output_dependencies(monkeypatch, include_output):
    profiles = list(IngestionProcessingProfile)
    selected = {profile: Mock() for profile in profiles}
    config = SimpleNamespace(
        processing=SimpleNamespace(
            default_profile=IngestionProcessingProfile.medium,
            profiles=SimpleNamespace(**{profile.value: SimpleNamespace(input_processors=[SimpleNamespace(suffix=".PDF", class_path=profile.value)]) for profile in profiles}),
        ),
        library_output_processors=[SimpleNamespace(class_path=f"{__name__}.LibraryProcessor")],
    )
    context = Mock()
    context.get_config.return_value = config
    context.get_output_processor_instance.side_effect = None if include_output else AssertionError("output dependency constructed")
    LibraryProcessor.constructed = 0
    monkeypatch.setattr(processing_pipeline, "EXTENSION_CATEGORY", {".pdf": "document"})
    monkeypatch.setattr(ProcessingPipelineManager, "_instantiate_input_processor", staticmethod(lambda name: selected[IngestionProcessingProfile(name)]))

    # Exercise the ordinary default too, so indexing cannot silently lose output.
    manager = ProcessingPipelineManager.create_with_default(context) if include_output else ProcessingPipelineManager.create_with_default(context, include_output=False)
    assert manager.get_pipeline_for_profile(None) is manager.get_pipeline_for_profile(IngestionProcessingProfile.medium)
    for profile in profiles:
        pipeline = manager.get_pipeline_for_profile(profile)
        assert pipeline.input_processors == {".pdf": selected[profile]}
        assert bool(pipeline.output_processors) is include_output
        assert bool(pipeline.library_output_processors) is include_output
    assert LibraryProcessor.constructed == int(include_output)
    assert context.get_output_processor_instance.call_count == int(include_output)


def test_extraction_child_requests_input_only_construction(monkeypatch, tmp_path):
    from knowledge_flow_backend import application_context
    from knowledge_flow_backend.common import config_loader
    from knowledge_flow_backend.features.scheduler import extraction_process

    context = Mock()
    context_class = Mock(return_value=context)
    context_class.get_instance.return_value = context
    monkeypatch.setattr(application_context, "ApplicationContext", context_class)
    monkeypatch.setattr(config_loader, "load_configuration", Mock())
    factory = Mock()
    monkeypatch.setattr(ProcessingPipelineManager, "create_with_default", factory)
    monkeypatch.setattr(extraction_process.os, "setsid", Mock())
    monkeypatch.setattr(extraction_process, "_install_parent_death_signal", Mock())
    exit_process = Mock()
    monkeypatch.setattr(extraction_process.os, "_exit", exit_process)
    monkeypatch.setattr(extraction_process.DocumentMetadata, "model_validate_json", Mock(return_value="metadata"))
    send = Mock()
    monkeypatch.setattr(extraction_process, "_send_outcome", send)
    request = SimpleNamespace(config_file=None, input_path=str(tmp_path / "input.pdf"), output_dir=str(tmp_path), metadata_json="{}", profile="rich")
    pipe = Mock()

    extraction_process._child_main(request, pipe, 1)

    factory.assert_called_once_with(context, include_output=False)
    factory.return_value.run_input.assert_called_once_with(input_path=tmp_path / "input.pdf", output_dir=tmp_path, metadata="metadata", profile="rich")
    send.assert_called_once_with(pipe, {"error": None, "permanent": False})
    exit_process.assert_called_once_with(0)
