# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Document and resource listings derive readability from readable folders."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import RebacDisabledResult, TagPermission
from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.resources.service import ResourceService
from knowledge_flow_backend.features.resources.structures import ResourceKind

pytestmark = pytest.mark.asyncio


class _FolderRebac:
    """Answers readable folders only; enumerating documents or resources is a bug."""

    def __init__(self, readable_tags):
        self.readable_tags = readable_tags

    async def lookup_user_resources(self, user, permission):
        assert permission == TagPermission.READ
        if self.readable_tags is None:
            return RebacDisabledResult()
        return [SimpleNamespace(id=tag_id) for tag_id in self.readable_tags]


def _doc(uid, tags):
    return DocumentMetadata(
        identity=Identity(document_uid=uid, document_name=f"{uid}.txt"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        tags=Tagging(tag_ids=tags),
    )


@pytest.mark.parametrize(("readable_tags", "expected"), [({"lib-a"}, ["in-a", "in-a-and-b"]), (None, ["in-a", "in-a-and-b", "in-b", "untagged"])])
async def test_document_listing_follows_readable_folders(readable_tags, expected):
    service = MetadataService.__new__(MetadataService)
    service.rebac = _FolderRebac(readable_tags)
    docs = [_doc("in-a", ["lib-a"]), _doc("in-a-and-b", ["lib-b", "lib-a"]), _doc("in-b", ["lib-b"]), _doc("untagged", [])]
    service.metadata_store = SimpleNamespace(get_all_metadata=AsyncMock(return_value=docs))

    listed = await service.get_documents_metadata(SimpleNamespace(uid="u-1"), {})

    assert [doc.document_uid for doc in listed] == expected


@pytest.mark.parametrize(("readable_tags", "expected"), [({"lib-a"}, ["prompt-a"]), (set(), []), (None, ["prompt-a", "prompt-b"])])
async def test_resource_listing_follows_readable_folders(readable_tags, expected):
    service = ResourceService.__new__(ResourceService)
    service.rebac = _FolderRebac(readable_tags)
    resources = [SimpleNamespace(id="prompt-a", library_tags=["lib-a"]), SimpleNamespace(id="prompt-b", library_tags=["lib-b"])]
    service._resource_store = SimpleNamespace(get_all_resources=AsyncMock(return_value=resources))

    listed = await service.list_resources_by_kind(kind=ResourceKind.PROMPT, user=SimpleNamespace(uid="u-1"))

    assert [resource.id for resource in listed] == expected
