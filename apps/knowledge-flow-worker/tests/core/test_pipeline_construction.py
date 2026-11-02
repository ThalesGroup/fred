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

from knowledge_flow_worker.common.structures import IngestionProcessingProfile
from knowledge_flow_worker.core import processing_pipeline
from knowledge_flow_worker.core.processing_pipeline_manager import ProcessingPipelineManager


@pytest.mark.parametrize("default_profile", list(IngestionProcessingProfile))
@pytest.mark.parametrize("include_output", [False, True])
def test_profile_construction_preserves_input_selection_without_output_dependencies(monkeypatch, include_output, default_profile):
    profiles = list(IngestionProcessingProfile)
    selected = {profile: Mock() for profile in profiles}
    config = SimpleNamespace(
        processing=SimpleNamespace(
            default_profile=default_profile,
            profiles=SimpleNamespace(**{profile.value: SimpleNamespace(input_processors=[SimpleNamespace(suffix=".PDF", class_path=profile.value)]) for profile in profiles}),
        ),
    )
    context = Mock()
    context.get_config.return_value = config
    context.get_output_processor_instance.side_effect = None if include_output else AssertionError("output dependency constructed")
    monkeypatch.setattr(processing_pipeline, "EXTENSION_CATEGORY", {".pdf": "document"})
    monkeypatch.setattr(ProcessingPipelineManager, "_instantiate_input_processor", staticmethod(lambda name: selected[IngestionProcessingProfile(name)]))

    # Exercise the ordinary default too, so indexing cannot silently lose output.
    manager = ProcessingPipelineManager.create_with_default(context) if include_output else ProcessingPipelineManager.create_with_default(context, include_output=False)
    assert manager.get_pipeline_for_profile(None) is manager.get_pipeline_for_profile(default_profile)
    for profile in profiles:
        pipeline = manager.get_pipeline_for_profile(profile)
        assert manager.get_pipeline_for_profile(profile.value) is pipeline
        assert pipeline.input_processors == {".pdf": selected[profile]}
        assert bool(pipeline.output_processors) is include_output
    assert context.get_output_processor_instance.call_count == int(include_output)
