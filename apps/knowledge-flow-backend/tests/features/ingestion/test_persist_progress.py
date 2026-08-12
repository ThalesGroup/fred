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

"""`IngestionService.persist_progress` — the single seam every ingestion write
goes through, and the one that compensates for a lost race (#2315).

An activity's work runs in a thread Python cannot kill, so it routinely
finishes after a cancellation deleted the document, having written content,
vectors or Parquet for a document that no longer exists. The conditional UPDATE
underneath tells the writer it lost; this is where it cleans up after itself.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", email="t@localhost", roles=[])


def _doc() -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name="report.pdf", document_uid="doc-1", title="report"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads", pull_location=None),
    )


class _SpyMetadataService:
    def __init__(self, *, persisted: bool) -> None:
        self._persisted = persisted
        self.purged: list[str] = []
        self.checked_updates = 0
        self.trusted_updates = 0

    async def update_document_metadata(self, user, metadata) -> bool:
        self.checked_updates += 1
        return self._persisted

    async def update_document_metadata_trusted(self, user, metadata) -> bool:
        self.trusted_updates += 1
        return self._persisted

    async def purge_document_artifacts(self, document_uid: str) -> None:
        self.purged.append(document_uid)


def _service(metadata_service) -> IngestionService:
    service = IngestionService.__new__(IngestionService)
    service.metadata_service = metadata_service
    service.context = SimpleNamespace()
    return service


@pytest.mark.asyncio
async def test_a_landed_write_leaves_the_artifacts_alone():
    spy = _SpyMetadataService(persisted=True)

    assert await _service(spy).persist_progress(_user(), _doc()) is True
    assert spy.purged == []


@pytest.mark.asyncio
async def test_a_lost_race_discards_the_artifacts_it_wrote():
    # The document was deleted under this activity: what it just wrote is an
    # orphan nothing points at, so the writer purges its own output.
    spy = _SpyMetadataService(persisted=False)

    assert await _service(spy).persist_progress(_user(), _doc()) is False
    assert spy.purged == ["doc-1"]


@pytest.mark.asyncio
async def test_the_trusted_variant_skips_the_permission_check_and_still_compensates():
    spy = _SpyMetadataService(persisted=False)

    assert await _service(spy).persist_progress_trusted(_user(), _doc()) is False
    assert spy.trusted_updates == 1
    assert spy.checked_updates == 0
    assert spy.purged == ["doc-1"]
