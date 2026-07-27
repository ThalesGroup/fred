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

"""MIGR-07 CSV/cross-team fix — regression guard for
`MetadataService.save_document_metadata_trusted`.

`save_document_metadata` does more than the per-tag `TagPermission.UPDATE`
check: it also prunes stale tabular Parquet artifacts, adjusts team storage
quotas, and updates tag timestamps (`_persist_metadata_and_follow_up`). A
naive "trusted bypass" that reimplemented the write instead of reusing that
shared helper could easily drop one of those follow-up steps silently — this
is exactly the regression this file guards against, by asserting both
`save_document_metadata` and `save_document_metadata_trusted` route through
the identical `_persist_metadata_and_follow_up`, and that only the permission
check differs.
"""

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
    """Rejects every permission check — simulates a root/platform admin with
    no per-tag/per-team grant, exactly the caller `save_document_metadata`
    (the checked path) would incorrectly reject for a cross-team document."""

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
    """Sanity/contrast: the ordinary, permission-checked path still enforces
    `TagPermission.UPDATE` — proving the trusted bypass below is a distinct,
    narrow addition, not a general weakening of `save_document_metadata`."""
    service = _build_service()
    metadata = _make_metadata("doc-1", tag_ids=["tag-other-team"])

    with pytest.raises(AuthorizationError):
        await service.save_document_metadata(user=object(), metadata=metadata)


@pytest.mark.asyncio
async def test_save_document_metadata_trusted_skips_the_permission_check_but_runs_the_same_follow_up():
    """The load-bearing guarantee: `save_document_metadata_trusted` never
    calls `check_user_permission_or_raise` (so a root/platform admin with no
    per-tag grant on a cross-team document still succeeds), but it reaches
    the exact same `_persist_metadata_and_follow_up` helper as the checked
    path — so Parquet pruning / storage-quota adjustment / tag-timestamp
    updates are never silently dropped for the trusted call."""
    service = _build_service()
    metadata = _make_metadata("doc-1", tag_ids=["tag-other-team"])
    calls: list[tuple[object, DocumentMetadata]] = []

    async def _fake_persist_and_follow_up(user, metadata) -> None:
        calls.append((user, metadata))

    service._persist_metadata_and_follow_up = _fake_persist_and_follow_up
    caller = object()

    await service.save_document_metadata_trusted(user=caller, metadata=metadata)

    assert calls == [(caller, metadata)]


@pytest.mark.asyncio
async def test_save_document_metadata_checked_also_routes_through_persist_and_follow_up():
    """Same shared helper, checked path — proves the two public methods are
    genuinely two thin entry points over one persistence implementation, not
    two independently-maintained copies that could drift apart."""

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
