from typing import Protocol

from fred_core import KeycloakUser

from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService
from knowledge_flow_backend.features.resources.service import ResourceService
from knowledge_flow_backend.features.tag.structure import TagType


class TagItemService(Protocol):
    """Common interface between all different tag items"""

    async def retrieve_items_ids_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]: ...

    async def add_tag_id_to_item(self, user: KeycloakUser, item_id: str, new_tag_id: str) -> None: ...

    async def remove_tag_id_from_item(self, user: KeycloakUser, item_id: str, tag_id_to_remove: str) -> None: ...


class DocumentTagItemService(TagItemService):
    """Allow to use DocumentMetadata as tag items"""

    def __init__(self):
        self.document_metadata_service = MetadataService()

    async def retrieve_items_ids_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        return [d.document_uid for d in await self.document_metadata_service.get_document_metadata_in_tag(user, tag_id)]

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


class ResourceTagItemService(TagItemService):
    """Allow to use Resources as tag items"""

    def __init__(self, tag_type: TagType):
        self.resource_kind = tag_type.to_resource_kind()
        self.resource_service = ResourceService()

    async def retrieve_items_ids_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        all_resources = self.resource_service.list_resources_by_kind(kind=self.resource_kind, user=user)
        return [res.id for res in all_resources if tag_id in res.library_tags]

    async def add_tag_id_to_item(self, user: KeycloakUser, item_id: str, new_tag_id: str) -> None:
        self.resource_service.add_tag_to_resource(user, item_id, new_tag_id)

    async def remove_tag_id_from_item(self, user: KeycloakUser, item_id: str, tag_id_to_remove: str) -> None:
        self.resource_service.remove_tag_from_resource(user, item_id, tag_id_to_remove)


def get_specific_tag_item_service(tag_type: TagType) -> TagItemService:
    """Return the good implementation of BaseTagItemService for a given TagType"""
    if tag_type == TagType.DOCUMENT:
        return DocumentTagItemService()
    else:
        # For now, apart for documents, all the other item a tag can contain are `Resources`
        return ResourceTagItemService(tag_type)
