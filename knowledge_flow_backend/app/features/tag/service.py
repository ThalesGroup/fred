# Copyright Thales 2025
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

# Copyright Thales 2025
import logging
from datetime import datetime
from typing import Iterable, Optional
from uuid import uuid4

from fred_core import Action, KeycloakUser, RebacReference, Relation, RelationType, Resource, TagPermission, authorize

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata
from app.core.stores.tags.base_tag_store import TagAlreadyExistsError
from app.features.metadata.service import MetadataService
from app.features.resources.service import ResourceService
from app.features.resources.structures import ResourceKind
from app.features.tag.structure import Tag, TagCreate, TagType, TagUpdate, TagWithItemsId, UserTagRelation

logger = logging.getLogger(__name__)


def _tagtype_to_rk(tag_type: TagType) -> ResourceKind:
    if tag_type == TagType.PROMPT:
        return ResourceKind.PROMPT
    if tag_type == TagType.TEMPLATE:
        return ResourceKind.TEMPLATE
    if tag_type == TagType.CHAT_CONTEXT:
        return ResourceKind.CHAT_CONTEXT
    raise ValueError(f"Unsupported TagType for resources: {tag_type}")


class TagService:
    """
    Service for Tag CRUD, user-scoped, with hierarchical path support.
    Documents & prompts still link by tag *id* (no change to metadata schema).
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self.document_metadata_service = MetadataService()
        self.resource_service = ResourceService()  # For templates, if needed
        self.rebac = context.get_rebac_engine()

    # ---------- Public API ----------

    @authorize(Action.READ, Resource.TAGS)
    def list_all_tags_for_user(
        self,
        user: KeycloakUser,
        tag_type: Optional[TagType] = None,
        path_prefix: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[TagWithItemsId]:
        """
        List user tags, optionally filtered by type and hierarchical prefix (e.g. 'Sales' or 'Sales/HR').
        Pagination included.
        """
        # 1) fetch
        tags: list[Tag] = self._tag_store.list_tags_for_user(user)

        # Filter by permission (todo: use rebac ids to filter at store (DB) level)
        authorized_tags_ids = [t.id for t in self.rebac.lookup_user_resources(user, TagPermission.READ)]
        tags = [t for t in tags if t.id in authorized_tags_ids]

        # 2) filter by type
        if tag_type is not None:
            tags = [t for t in tags if t.type == tag_type]

        # 3) filter by path prefix (match both path itself and leaf)
        if path_prefix:
            prefix = self._normalize_path(path_prefix)
            if prefix:
                tags = [t for t in tags if self._full_path_of(t).startswith(prefix)]

        # 4) stable sort by full_path (optional but nice for UI determinism)
        tags.sort(key=lambda t: self._full_path_of(t).lower())

        # 5) paginate
        sliced = tags[offset : offset + limit]

        # 6) attach item ids
        result: list[TagWithItemsId] = []
        for tag in sliced:
            if tag.type == TagType.DOCUMENT:
                item_ids = self._retrieve_document_ids_for_tag(user, tag.id)
            elif tag.type == TagType.PROMPT:
                item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.PROMPT, tag.id)
            elif tag.type == TagType.TEMPLATE:
                item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.TEMPLATE, tag.id)
            elif tag.type == TagType.CHAT_CONTEXT:
                item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.CHAT_CONTEXT, tag.id)
            else:
                raise ValueError(f"Unsupported tag type: {tag.type}")
            result.append(TagWithItemsId.from_tag(tag, item_ids))
        return result

    @authorize(Action.READ, Resource.TAGS)
    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        self.rebac.check_user_permission_or_raise(user, TagPermission.READ, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)
        if tag.type == TagType.DOCUMENT:
            item_ids = self._retrieve_document_ids_for_tag(user, tag_id)
        elif tag.type == TagType.PROMPT:
            item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.PROMPT, tag.id)
        elif tag.type == TagType.TEMPLATE:
            item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.TEMPLATE, tag.id)
        elif tag.type == TagType.CHAT_CONTEXT:
            item_ids = self.resource_service.get_resource_ids_for_tag(ResourceKind.CHAT_CONTEXT, tag.id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")
        return TagWithItemsId.from_tag(tag, item_ids)

    @authorize(Action.CREATE, Resource.TAGS)
    def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        # Validate referenced items first
        if tag_data.type == TagType.DOCUMENT:
            documents = self._retrieve_documents_metadata(user, tag_data.item_ids)
        elif tag_data.type in (TagType.PROMPT, TagType.TEMPLATE, TagType.CHAT_CONTEXT):
            documents = []  # not used here
        else:
            raise ValueError(f"Unsupported tag type: {tag_data.type}")

        # Normalize + uniqueness
        norm_path = self._normalize_path(tag_data.path)
        full_path = self._compose_full_path(norm_path, tag_data.name)
        self._ensure_unique_full_path(owner_id=user.uid, tag_type=tag_data.type, full_path=full_path)

        now = datetime.now()
        tag = self._tag_store.create_tag(
            Tag(
                id=str(uuid4()),
                owner_id=user.uid,
                created_at=now,
                updated_at=now,
                name=tag_data.name,
                path=norm_path,
                description=tag_data.description,
                type=tag_data.type,
            )
        )
        consistency_token = self.rebac.add_user_relation(user, RelationType.OWNER, resource_type=Resource.TAGS, resource_id=tag.id)

        # Link items
        if tag.type == TagType.DOCUMENT:
            for doc in documents:
                self.document_metadata_service.add_tag_id_to_document(
                    user,
                    metadata=doc,
                    new_tag_id=tag.id,
                    consistency_token=consistency_token,
                )
        elif tag.type in (TagType.PROMPT, TagType.TEMPLATE):
            # rk = _tagtype_to_rk(tag.type)
            for rid in tag_data.item_ids:
                try:
                    self.resource_service.add_tag_to_resource(rid, tag.id)
                except Exception as e:
                    logger.warning(f"Failed to attach tag {tag.id} to resource {rid}: {e}")
                    raise

        return TagWithItemsId.from_tag(tag, tag_data.item_ids)

    @authorize(Action.UPDATE, Resource.TAGS)
    def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)

        # Update memberships first
        if tag.type == TagType.DOCUMENT:
            old_item_ids = self._retrieve_document_ids_for_tag(user, tag_id)
            added, removed = self._compute_ids_diff(old_item_ids, tag_data.item_ids)

            added_documents = self._retrieve_documents_metadata(user, added)
            removed_documents = self._retrieve_documents_metadata(user, removed)
            for doc in added_documents:
                self.document_metadata_service.add_tag_id_to_document(user, doc, tag.id)
            for doc in removed_documents:
                self.document_metadata_service.remove_tag_id_from_document(user, doc, tag.id)

        elif tag.type in (TagType.PROMPT, TagType.TEMPLATE, TagType.CHAT_CONTEXT):
            rk = _tagtype_to_rk(tag.type)
            old_item_ids = self.resource_service.get_resource_ids_for_tag(rk, tag_id)
            added, removed = self._compute_ids_diff(old_item_ids, tag_data.item_ids)

            for rid in added:
                try:
                    self.resource_service.add_tag_to_resource(rid, tag_id)
                except Exception:
                    # Decide whether to continue or fail fast
                    raise
            for rid in removed:
                try:
                    # auto-delete orphan if it loses its last tag
                    self.resource_service.remove_tag_from_resource(rid, tag_id, delete_if_orphan=True)
                except Exception:
                    raise
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")

        tag.updated_at = datetime.now()
        updated_tag = self._tag_store.update_tag_by_id(tag_id, tag)

        # For the response, return the up-to-date list of item ids
        if tag.type == TagType.DOCUMENT:
            item_ids = self._retrieve_document_ids_for_tag(user, tag_id)
        elif tag.type in (TagType.PROMPT, TagType.TEMPLATE):
            rk = _tagtype_to_rk(tag.type)
            item_ids = self.resource_service.get_resource_ids_for_tag(rk, tag_id)
        else:
            item_ids = []

        return TagWithItemsId.from_tag(updated_tag, item_ids)

    @authorize(Action.DELETE, Resource.TAGS)
    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        self.rebac.check_user_permission_or_raise(user, TagPermission.DELETE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)

        if tag.type == TagType.DOCUMENT:
            documents = self._retrieve_documents_for_tag(user, tag_id)
            for doc in documents:
                self.document_metadata_service.remove_tag_id_from_document(user, doc, tag_id)
        elif tag.type == TagType.PROMPT:
            self.resource_service.remove_tag_from_resources(ResourceKind.PROMPT, tag_id)
        elif tag.type == TagType.CHAT_CONTEXT:
            self.resource_service.remove_tag_from_resources(ResourceKind.CHAT_CONTEXT, tag_id)
        elif tag.type == TagType.TEMPLATE:
            # BUGFIX: was PROMPT before; must be TEMPLATE
            self.resource_service.remove_tag_from_resources(ResourceKind.TEMPLATE, tag_id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")

        self._tag_store.delete_tag_by_id(tag_id)
        # TODO: remove relation in ReBAC

    def share_tag_with_user(self, user: KeycloakUser, tag_id: str, target_user_id: str, relation: UserTagRelation) -> None:
        """
        Share a tag with another user by adding a relation in the ReBAC engine.
        """
        self.rebac.check_user_permission_or_raise(user, TagPermission.SHARE, tag_id)
        self.rebac.add_relation(
            Relation(
                subject=RebacReference(type=Resource.USER, id=target_user_id),
                relation=relation.to_relation(),
                resource=RebacReference(type=Resource.TAGS, id=tag_id),
            )
        )

    def unshare_tag_with_user(self, user: KeycloakUser, tag_id: str, target_user_id: str) -> None:
        """
        Revoke tag access previously granted to another user.
        Removes any user-tag relation regardless of the level originally assigned.
        """
        self.rebac.check_user_permission_or_raise(user, TagPermission.SHARE, tag_id)
        for relation in UserTagRelation:
            self.rebac.delete_relation(
                Relation(
                    subject=RebacReference(type=Resource.USER, id=target_user_id),
                    relation=relation.to_relation(),
                    resource=RebacReference(type=Resource.TAGS, id=tag_id),
                )
            )

    @authorize(Action.UPDATE, Resource.TAGS)
    def update_tag_timestamp(self, tag_id: str, user: KeycloakUser) -> None:
        self.rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

        tag = self._tag_store.get_tag_by_id(tag_id)
        tag.updated_at = datetime.now()
        self._tag_store.update_tag_by_id(tag_id, tag)

    # ---------- Internals / helpers ----------

    def _retrieve_documents_for_tag(self, user: KeycloakUser, tag_id: str) -> list[DocumentMetadata]:
        return self.document_metadata_service.get_document_metadata_in_tag(user, tag_id)

    def _retrieve_document_ids_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        return [d.document_uid for d in self._retrieve_documents_for_tag(user, tag_id)]

    def _retrieve_documents_metadata(self, user: KeycloakUser, document_ids: Iterable[str]) -> list[DocumentMetadata]:
        return [self.document_metadata_service.get_document_metadata(user, doc_id) for doc_id in document_ids]

    @staticmethod
    def _compute_ids_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
        b, a = set(before), set(after)
        return list(a - b), list(b - a)

    @staticmethod
    def _normalize_path(path: Optional[str]) -> str | None:
        if path is None:
            return None
        parts = [seg.strip() for seg in path.split("/") if seg.strip()]
        return "/".join(parts) or None

    @staticmethod
    def _compose_full_path(path: Optional[str], name: str) -> str:
        return f"{path}/{name}" if path else name

    def _full_path_of(self, tag: Tag) -> str:
        return self._compose_full_path(tag.path, tag.name)

    def _ensure_unique_full_path(
        self,
        owner_id: str,
        tag_type: TagType,
        full_path: str,
        exclude_tag_id: Optional[str] = None,
    ) -> None:
        """
        Check uniqueness of (owner_id, type, full_path). Prefer delegating to the store if it exposes a method.
        """
        existing = self._tag_store.get_by_owner_type_full_path(owner_id, tag_type, full_path)
        if existing and existing.id != (exclude_tag_id or ""):
            if existing.type == tag_type:
                raise TagAlreadyExistsError(f"Tag '{full_path}' already exists for owner {owner_id} and type {tag_type}.")
        return
