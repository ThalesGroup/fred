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

"""Folder-size aggregation (`total_size_by_tags`) — the reliable, non-paginated
total that backs the collapsed-folder size label in the resources UI."""

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)

from tests.conftest import _InMemoryTestMetadataStore


def _doc(uid: str, size: int | None, tag_ids: list[str]) -> DocumentMetadata:
    kwargs = dict(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        tags=Tagging(tag_ids=tag_ids),
    )
    if size is not None:
        kwargs["file"] = FileInfo(file_size_bytes=size)
    return DocumentMetadata(**kwargs)


@pytest.mark.asyncio
async def test_total_size_by_tags_sums_per_tag_over_the_whole_folder():
    store = _InMemoryTestMetadataStore()
    await store.save_metadata(_doc("a", 100, ["t1"]))
    # A document can belong to several folders — its size counts in each.
    await store.save_metadata(_doc("b", 250, ["t1", "t2"]))
    # Missing size counts as 0, never raises.
    await store.save_metadata(_doc("c", None, ["t2"]))

    sizes = await store.total_size_by_tags(["t1", "t2", "t3"])

    # t1 = 100 + 250, t2 = 250 + 0, t3 has no documents → 0 (present, not absent).
    assert sizes == {"t1": 350, "t2": 250, "t3": 0}


@pytest.mark.asyncio
async def test_total_size_by_tags_empty_request_returns_empty():
    store = _InMemoryTestMetadataStore()
    await store.save_metadata(_doc("a", 100, ["t1"]))

    assert await store.total_size_by_tags([]) == {}
