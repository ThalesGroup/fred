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

from fred_core import KeycloakUser

from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService


class DocumentTagItemService:
    """Allow to use DocumentMetadata as tag items"""

    def __init__(self):
        self.document_metadata_service = MetadataService()

    async def retrieve_items_ids_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        return [d.document_uid for d in await self.document_metadata_service.get_document_metadata_in_tag(user, tag_id)]

    async def retrieve_items_ids_for_tags(self, user: KeycloakUser, tag_ids: list[str]) -> dict[str, list[str]]:
        return await self.document_metadata_service.get_document_uids_in_tags(user, tag_ids)

    async def add_tag_id_to_item(self, user: KeycloakUser, item_id: str, new_tag_id: str) -> None:
        doc = await self.document_metadata_service.get_document_metadata(user, item_id)
        await self.document_metadata_service.add_tag_id_to_document(user, doc, new_tag_id)

    async def remove_tag_id_from_item(self, user: KeycloakUser, item_id: str, tag_id_to_remove: str) -> None:
        try:
            doc = await self.document_metadata_service.get_document_metadata(user, item_id)
        except MetadataNotFound:
            # If the document no longer exists, removing a tag from it is a no-op.
            # This can happen when metadata has been cleaned up after prior operations.
            return
        await self.document_metadata_service.remove_tag_id_from_document(user, doc, tag_id_to_remove)
