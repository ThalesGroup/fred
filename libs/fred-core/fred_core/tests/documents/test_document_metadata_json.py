# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The worker and API share metadata.json without the historical SQL stores."""

import json

import pytest
from fred_core import DocumentMetadata, Identity, ProcessingStage, ProcessingStatus
from fred_core.documents import SourceInfo, SourceType
from fred_core.documents.processing_profile import IngestionProcessingProfile


@pytest.mark.parametrize("profile", ["fast", "medium", "rich"])
def test_processing_profile_and_stages_round_trip_in_metadata_json(profile):
    metadata = DocumentMetadata(
        identity=Identity(document_name="data.csv", document_uid="doc-1"),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
        ),
        labels=["DAT"],
    )
    metadata.processing.profile = IngestionProcessingProfile(profile)
    metadata.processing.mark_done(ProcessingStage.SQL_INDEXED)

    payload = metadata.model_dump_json()
    restored = DocumentMetadata.model_validate_json(payload)

    assert json.loads(payload)["processing"]["profile"] == profile
    assert restored.processing.profile is IngestionProcessingProfile(profile)
    assert (
        restored.processing.stages[ProcessingStage.SQL_INDEXED] is ProcessingStatus.DONE
    )
    assert restored.labels == ["DAT"]
    assert restored == metadata
