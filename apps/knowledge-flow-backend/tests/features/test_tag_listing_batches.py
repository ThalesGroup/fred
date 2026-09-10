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

"""Listing libraries must not fan out per library.

Attaching `item_ids` used to run one authorization lookup and one metadata
scan per tag, so opening the resources page cost N of each for N folders even
though the authorization answer is per user and identical every time. This
pins the call counts, not just the result: the payload looks the same either
way, so only counting reads can stop the loop coming back. The same guard for
the corpus stats aggregate lives in tests/services/test_tag_service_type_stats.py.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.core.stores.tags.base_tag_store import BaseTagStore, TagNotFoundError
from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService


def _doc(uid: str, name: str, tag_ids: list[str], size: int = 10) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        tags=Tagging(tag_ids=tag_ids),
        file=FileInfo(file_size_bytes=size),
    )


class _InMemoryTagStore(BaseTagStore):
    """The test configuration wires tag storage to duckdb, which the context
    cannot build — these tests only ever create and list."""

    def __init__(self):
        self._tags: dict[str, Tag] = {}

    async def list_all_tags(self, session=None) -> list[Tag]:
        return list(self._tags.values())

    async def get_tag_by_id(self, tag_id: str, session=None) -> Tag:
        if tag_id not in self._tags:
            raise TagNotFoundError(tag_id)
        return self._tags[tag_id]

    async def get_by_owner_type_full_path(self, owner_id, tag_type, full_path, session=None):
        return None

    async def create_tag(self, tag: Tag, session=None) -> Tag:
        self._tags[tag.id] = tag
        return tag

    async def update_tag_by_id(self, tag_id: str, tag: Tag, session=None) -> Tag:
        self._tags[tag_id] = tag
        return tag

    async def delete_tag_by_id(self, tag_id: str, session=None) -> None:
        self._tags.pop(tag_id, None)


class _CountingStore:
    """Delegates to the real store, counting the reads this change is about."""

    def __init__(self, inner):
        self._inner = inner
        self.per_tag_reads = 0
        self.batched_reads = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def get_metadata_in_tag(self, tag_id, session=None):
        self.per_tag_reads += 1
        return await self._inner.get_metadata_in_tag(tag_id, session=session)

    async def document_uids_by_tags(self, tag_ids, session=None):
        self.batched_reads += 1
        return await self._inner.document_uids_by_tags(tag_ids, session=session)


async def _seed(service: TagService, user, tag_count: int) -> list[str]:
    tag_ids = []
    for i in range(tag_count):
        now = datetime.now(timezone.utc)
        tag = Tag(id=str(uuid4()), name=f"lib{i}", type=TagType.DOCUMENT, owner_id=user.uid, created_at=now, updated_at=now)
        await service._tag_store.create_tag(tag)
        tag_ids.append(tag.id)
        await service.document_metadata_service.metadata_store.save_metadata(_doc(f"d{i}", f"d{i}.pdf", [tag.id]))
    return tag_ids


@pytest.fixture
def fake_user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", roles=["admin"], email="t@example.com")


@pytest.fixture
def counting_store(app_context):
    ctx = app_context.get_instance()
    store = _CountingStore(ctx.get_metadata_store())
    ctx._metadata_store_instance = store
    ctx._tag_store_instance = _InMemoryTagStore()
    # TagService builds a ResourceService, whose store the test configuration
    # cannot construct either. Never touched: these tests list document tags.
    ctx._resource_store_instance = object()
    return store


@pytest.mark.asyncio
async def test_listing_tags_reads_item_ids_once_for_every_folder(counting_store, fake_user):
    service = TagService()
    tag_ids = await _seed(service, fake_user, tag_count=5)

    tags = await service.list_all_tags_for_user(fake_user, tag_type=TagType.DOCUMENT)

    # One batched read for the five libraries, and none of the per-tag reads.
    assert counting_store.batched_reads == 1
    assert counting_store.per_tag_reads == 0
    by_id = {t.id: t for t in tags}
    for i, tag_id in enumerate(tag_ids):
        assert by_id[tag_id].item_ids == [f"d{i}"]
