# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Real mail input pipeline and manager serialization; transport is driven by Rust.

No model, database or network is used here. The caller publishes these exact bytes
through the real Control Plane against disposable PostgreSQL/object storage.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fred_core.documents.document_structures import DocumentMetadata, FileInfo, Identity, SourceInfo, SourceType
from knowledge_flow_worker.core.processing_pipeline import ProcessingPipeline
from knowledge_flow_worker.core.processing_pipeline_manager import ProcessingPipelineManager
from knowledge_flow_worker.features.manager_processing import service
from knowledge_flow_worker.features.manager_processing.artifacts import describe
from knowledge_flow_worker.features.manager_processing.contracts import Descriptor, Manifest
from knowledge_flow_worker.features.manager_processing.service import ManagedIngestionService

job, original, output = map(Path, sys.argv[1:])
descriptor = Descriptor.model_validate_json(job.read_text())
output.mkdir()
entry = next(entry for entry in descriptor.profile_settings["input_processors"] if entry["suffix"] == original.suffix)
pipeline = ProcessingPipeline(name="email", input_processors={original.suffix: ProcessingPipelineManager._instantiate_input_processor(entry["class_path"])}, output_processors={})
metadata = DocumentMetadata(
    identity=Identity(document_uid=str(descriptor.work.document_id), document_name=descriptor.name, uploaded_by=descriptor.actor),
    source=SourceInfo(source_type=SourceType.PUSH, retrievable=False),
    file=FileInfo(sha256=descriptor.work.original_sha256),
)
pipeline.process_input(original, output, metadata.model_copy(deep=True))


def publish(d, directory, **counts):
    return Manifest(generation=d.generation, artifacts=[describe(path, path.name) for path in directory.iterdir()], **counts)


class Callback:
    def __init__(self, *_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def post(self, path, body):
        (output.parent / "commit.json").write_text(body.model_dump_json())


service.ManagerClient = Callback
worker = ManagedIngestionService.__new__(ManagedIngestionService)
worker.descriptor = descriptor
worker.settings = SimpleNamespace()
worker.artifacts = SimpleNamespace(publish=publish)
worker.vectors = None
worker.save_output(None, metadata, output)
assert json.loads((output / "metadata.json").read_text())["extensions"]["email"]
