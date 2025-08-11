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
from datetime import datetime
from typing import Optional, Iterable
from uuid import uuid4

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata
from app.core.stores.tags.base_tag_store import TagAlreadyExistsError
from app.features.metadata.service import MetadataService
from app.features.prompts.service import PromptService
from app.features.prompts.structure import Prompt
from app.features.tag.structure import Tag, TagCreate, TagType, TagUpdate, TagWithItemsId
from fred_core import KeycloakUser


class TagService:
    """
    Service for Tag CRUD, user-scoped, with hierarchical path support.
    Documents & prompts still link by tag *id* (no change to metadata schema).
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._tag_store = context.get_tag_store()
        self.document_metadata_service = MetadataService()
        self.prompt_service = PromptService()

    # ---------- Public API ----------

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
                item_ids = self._retrieve_document_ids_for_tag(tag.id)
            elif tag.type == TagType.PROMPT:
                item_ids = self._retrieve_prompt_ids_for_tag(tag.id)
            else:
                raise ValueError(f"Unsupported tag type: {tag.type}")
            result.append(TagWithItemsId.from_tag(tag, item_ids))
        return result

    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagWithItemsId:
        tag = self._tag_store.get_tag_by_id(tag_id)
        if tag.type == TagType.DOCUMENT:
            item_ids = self._retrieve_document_ids_for_tag(tag_id)
        elif tag.type == TagType.PROMPT:
            item_ids = self._retrieve_prompt_ids_for_tag(tag_id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")
        return TagWithItemsId.from_tag(tag, item_ids)

    def create_tag_for_user(self, tag_data: TagCreate, user: KeycloakUser) -> TagWithItemsId:
        # Validate referenced items first
        if tag_data.type == TagType.DOCUMENT:
            documents = self._retrieve_documents_metadata(tag_data.item_ids)
        elif tag_data.type == TagType.PROMPT:
            # Lazy validation: you can fetch prompts here if you want strict 404s
            documents = []  # keep var name for symmetry; not used for prompts
        else:
            raise ValueError(f"Unsupported tag type: {tag_data.type}")

        # Normalize/compute canonical path
        norm_path = self._normalize_path(tag_data.path)
        full_path = self._compose_full_path(norm_path, tag_data.name)

        # Enforce uniqueness per owner + type + full_path
        self._ensure_unique_full_path(owner_id=user.uid, tag_type=tag_data.type, full_path=full_path, user=user)

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

        # Link items (by tag id) — unchanged behavior
        if tag.type == TagType.DOCUMENT:
            for doc in documents:
                self.document_metadata_service.add_tag_id_to_document(
                    metadata=doc,
                    new_tag_id=tag.id,
                    modified_by=user.username,
                )
        elif tag.type == TagType.PROMPT:
            for prompt_id in tag_data.item_ids:
                self.prompt_service.add_tag_to_prompt(prompt_id, tag.id)

        return TagWithItemsId.from_tag(tag, tag_data.item_ids)

    def update_tag_for_user(self, tag_id: str, tag_data: TagUpdate, user: KeycloakUser) -> TagWithItemsId:
        tag = self._tag_store.get_tag_by_id(tag_id)

        # Update item memberships first (unchanged behavior)
        if tag.type == TagType.DOCUMENT:
            old_item_ids = self._retrieve_document_ids_for_tag(tag_id)
            added, removed = self._compute_ids_diff(old_item_ids, tag_data.item_ids)

            added_documents = self._retrieve_documents_metadata(added)
            removed_documents = self._retrieve_documents_metadata(removed)

            for doc in added_documents:
                self.document_metadata_service.add_tag_id_to_document(doc, tag.id, modified_by=user.username)
            for doc in removed_documents:
                self.document_metadata_service.remove_tag_id_from_document(doc, tag.id, modified_by=user.username)

        elif tag.type == TagType.PROMPT:
            old_item_ids = self._retrieve_prompt_ids_for_tag(tag_id)
            added, removed = self._compute_ids_diff(old_item_ids, tag_data.item_ids)
            for pid in added:
                self.prompt_service.add_tag_to_prompt(pid, tag_id)
            for pid in removed:
                self.prompt_service.remove_tag_from_prompt(pid, tag_id)

        # Rename / move (hierarchy)
        # NOTE: TagUpdate now supports optional path if you added it.
        new_name = tag_data.name
        new_path = getattr(tag_data, "path", None)  # keep compatible if controller didn’t add 'path' yet
        norm_path = self._normalize_path(new_path)

        # If moved/renamed, enforce uniqueness on the new canonical path
        new_full_path = self._compose_full_path(norm_path, new_name)
        old_full_path = self._full_path_of(tag)
        if new_full_path != old_full_path:
            self._ensure_unique_full_path(owner_id=tag.owner_id, tag_type=tag.type, full_path=new_full_path, exclude_tag_id=tag.id, user=user)

        tag.name = new_name
        tag.path = norm_path
        tag.description = tag_data.description
        tag.updated_at = datetime.now()
        updated_tag = self._tag_store.update_tag_by_id(tag_id, tag)

        return TagWithItemsId.from_tag(updated_tag, tag_data.item_ids)

    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        tag = self._tag_store.get_tag_by_id(tag_id)

        if tag.type == TagType.DOCUMENT:
            documents = self._retrieve_documents_for_tag(tag_id)
            for doc in documents:
                self.document_metadata_service.remove_tag_id_from_document(doc, tag_id, modified_by=user.username)
        elif tag.type == TagType.PROMPT:
            prompts = self._retrieve_prompts_for_tag(tag_id)
            for prompt in prompts:
                self.prompt_service.remove_tag_from_prompt(prompt.id, tag_id)
        else:
            raise ValueError(f"Unsupported tag type: {tag.type}")

        self._tag_store.delete_tag_by_id(tag_id)

    def update_tag_timestamp(self, tag_id: str) -> None:
        tag = self._tag_store.get_tag_by_id(tag_id)
        tag.updated_at = datetime.now()
        self._tag_store.update_tag_by_id(tag_id, tag)

    # ---------- Internals / helpers ----------

    def _retrieve_documents_for_tag(self, tag_id: str) -> list[DocumentMetadata]:
        return self.document_metadata_service.get_document_metadata_in_tag(tag_id)

    def _retrieve_prompts_for_tag(self, tag_id: str) -> list[Prompt]:
        return self.prompt_service.get_prompt_in_tag(tag_id)

    def _retrieve_document_ids_for_tag(self, tag_id: str) -> list[str]:
        return [d.document_uid for d in self._retrieve_documents_for_tag(tag_id)]

    def _retrieve_prompt_ids_for_tag(self, tag_id: str) -> list[str]:
        return [p.id for p in self._retrieve_prompts_for_tag(tag_id)]

    def _retrieve_documents_metadata(self, document_ids: Iterable[str]) -> list[DocumentMetadata]:
        return [self.document_metadata_service.get_document_metadata(doc_id) for doc_id in document_ids]

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
        user: KeycloakUser,
        exclude_tag_id: Optional[str] = None,
    ) -> None:
        """
        Check uniqueness of (owner_id, type, full_path). Prefer delegating to the store if it exposes a method.
        """
        existing = self._tag_store.get_by_owner_type_full_path(owner_id, tag_type, full_path)
        if existing and existing.id != (exclude_tag_id or ""):
            raise TagAlreadyExistsError(f"Tag '{full_path}' already exists for owner {owner_id} and type {tag_type}.")
        return
