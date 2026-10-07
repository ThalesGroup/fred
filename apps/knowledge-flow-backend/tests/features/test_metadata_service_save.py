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

"""Permission and persistence checks for metadata saves."""

from datetime import datetime, timezone

import pytest
from fred_core import AuthorizationError, Resource
from fred_core.documents.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.features.metadata.service import MetadataService


def _make_metadata(uid: str, *, tag_ids: list[str]) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.csv", document_uid=uid, modified=datetime.now(timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads", date_added_to_kb=datetime.now(timezone.utc)),
        file=FileInfo(),
        tags=Tagging(tag_ids=tag_ids),
        processing=Processing(),
        access=AccessInfo(),
    )


class _RejectingRebac:
    """Reject every per-tag permission check."""

    async def check_user_permission_or_raise(self, user, permission, resource_id) -> None:
        raise AuthorizationError(
            getattr(user, "uid", "unknown"),
            str(permission),
            Resource.TAGS,
            f"not authorized on {resource_id}",
        )


def _build_service() -> MetadataService:
    service = MetadataService.__new__(MetadataService)
    service.rebac = _RejectingRebac()
    return service


@pytest.mark.asyncio
async def test_save_document_metadata_checked_rejects_a_caller_without_tag_permission():
    """The ordinary save path enforces `TagPermission.UPDATE`."""
    service = _build_service()
    metadata = _make_metadata("doc-1", tag_ids=["tag-other-team"])

    with pytest.raises(AuthorizationError):
        await service.save_document_metadata(user=object(), metadata=metadata)


@pytest.mark.asyncio
async def test_save_document_metadata_checked_also_routes_through_persist_and_follow_up():
    """A permitted save still runs the shared metadata follow-up path."""

    class _PermissiveRebac:
        async def check_user_permission_or_raise(self, user, permission, resource_id) -> None:
            return None

    service = MetadataService.__new__(MetadataService)
    service.rebac = _PermissiveRebac()
    metadata = _make_metadata("doc-1", tag_ids=["tag-own-team"])
    calls: list[tuple[object, DocumentMetadata]] = []

    async def _fake_persist_and_follow_up(user, metadata) -> None:
        calls.append((user, metadata))

    service._persist_metadata_and_follow_up = _fake_persist_and_follow_up
    caller = object()

    await service.save_document_metadata(user=caller, metadata=metadata)

    assert calls == [(caller, metadata)]
